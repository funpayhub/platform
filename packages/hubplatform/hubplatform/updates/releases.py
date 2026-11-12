"""Installation layout: the file part of the launcher protocol (see :mod:`hubplatform.runtime`).

::

    releases/
        1.4.0/              app code, lib/ (first-party packages), release.json, .installed
        1.5.0/
        .downloads/         downloaded archives (app)
        state.json          current / previous release (written by the launcher only)
        staged.json         release to switch to on ExitCodes.UPDATE (written by the app only)
        result.json         outcome of the last switch (launcher writes, app removes)
    runtimes/
        rt-3f9a1c2b7d4e/    python/ (interpreter + third-party packages), runtime.json,
                            constraints.txt, .installed
    envs/
        rt-3f9a1c2b7d4e/    optional venv (--system-site-packages) on top of the runtime,
                            for plugin packages; used by the launcher if it exists

A release / runtime directory is complete only when its ``.installed`` marker exists;
anything else is a leftover of an interrupted installation and may be removed.
Releases and runtimes are installed by the app and removed by the launcher.

Each file has a single writer, so the app and the launcher never write the same file.
All files are written atomically (temporary file + rename).
"""

from __future__ import annotations


__all__ = [
    'RELEASES_SCHEMA',
    'ReleaseState',
    'UpdateResult',
    'Installation',
    'write_json_atomic',
    'replace_with_retry',
    'runtime_python',
]

import os
import sys
import json
import time
import secrets
from typing import Any, Literal
from dataclasses import dataclass
from pathlib import Path
from datetime import UTC, datetime

from packaging.version import Version, InvalidVersion


RELEASES_SCHEMA = 1
"""Version of the files format."""

_REPLACE_ATTEMPTS = 10
_REPLACE_DELAY = 0.5


@dataclass(frozen=True)
class ReleaseState:
    """Content of ``state.json``."""

    current: Version
    previous: Version | None
    pending: bool
    """Current release has not confirmed it starts yet (it was just switched to)."""
    attempts: int
    """Failed starts of a pending release."""
    failed: tuple[Version, ...]
    """Releases that were rolled back."""

    @classmethod
    def from_json(cls, data: Any) -> ReleaseState:
        try:
            return cls(
                current=Version(data['current']),
                previous=Version(data['previous']) if data.get('previous') else None,
                pending=bool(data.get('pending', False)),
                attempts=int(data.get('attempts', 0)),
                failed=tuple(Version(i) for i in data.get('failed', ())),
            )
        except (KeyError, TypeError, ValueError, InvalidVersion) as e:
            raise ValueError(f'Invalid releases state: {data!r}.') from e


@dataclass(frozen=True)
class UpdateResult:
    """Content of ``result.json``."""

    status: Literal['updated', 'rolled_back', 'failed']
    """
    * ``updated``: switched to ``version`` (from ``previous``);
    * ``rolled_back``: ``version`` failed to start, switched back to ``previous``;
    * ``failed``: could not switch to ``version``, still on ``previous``.
    """
    version: Version
    previous: Version | None
    message: str | None

    @classmethod
    def from_json(cls, data: Any) -> UpdateResult:
        try:
            status = data['status']
            if status not in ('updated', 'rolled_back', 'failed'):
                raise ValueError(f'Unknown status {status!r}.')
            return cls(
                status=status,
                version=Version(data['version']),
                previous=Version(data['previous']) if data.get('previous') else None,
                message=data.get('message') or None,
            )
        except (KeyError, TypeError, ValueError, InvalidVersion) as e:
            raise ValueError(f'Invalid update result: {data!r}.') from e


class Installation:
    """Releases, runtimes and environments on disk, as seen by the app."""

    STATE_FILE = 'state.json'
    STAGED_FILE = 'staged.json'
    RESULT_FILE = 'result.json'
    DOWNLOADS_DIR = '.downloads'
    MARKER_FILE = '.installed'
    TEMP_PREFIX = '.tmp-'

    def __init__(
        self,
        releases_dir: str | Path,
        runtimes_dir: str | Path,
        envs_dir: str | Path,
    ) -> None:
        self._releases_dir = Path(releases_dir).expanduser().resolve()
        self._runtimes_dir = Path(runtimes_dir).expanduser().resolve()
        self._envs_dir = Path(envs_dir).expanduser().resolve()

    @property
    def releases_dir(self) -> Path:
        return self._releases_dir

    @property
    def runtimes_dir(self) -> Path:
        return self._runtimes_dir

    @property
    def envs_dir(self) -> Path:
        return self._envs_dir

    @property
    def downloads_dir(self) -> Path:
        return self._releases_dir / self.DOWNLOADS_DIR

    def release_dir(self, version: Version) -> Path:
        return self._releases_dir / str(version)

    def runtime_dir(self, runtime_id: str) -> Path:
        return self._runtimes_dir / runtime_id

    def is_release_installed(self, version: Version) -> bool:
        return (self.release_dir(version) / self.MARKER_FILE).is_file()

    def is_runtime_installed(self, runtime_id: str) -> bool:
        return (self.runtime_dir(runtime_id) / self.MARKER_FILE).is_file()

    def installed_releases(self) -> tuple[Version, ...]:
        """Installed releases, newest first."""
        if not self._releases_dir.is_dir():
            return ()
        result: list[Version] = []
        for i in self._releases_dir.iterdir():
            try:
                version = Version(i.name)
            except InvalidVersion:
                continue
            if str(version) == i.name and self.is_release_installed(version):
                result.append(version)
        return tuple(sorted(result, reverse=True))

    @staticmethod
    def mark_installed(directory: Path, sha256: str) -> None:
        write_json_atomic(
            directory / Installation.MARKER_FILE,
            {
                'schema': RELEASES_SCHEMA,
                'sha256': sha256,
                'installed_at': datetime.now(UTC).isoformat(),
            },
        )

    def temp_dir(self, parent: Path, name: str) -> Path:
        """New unique temporary directory path in ``parent``."""
        return parent / f'{self.TEMP_PREFIX}{name}-{secrets.token_hex(8)}'

    def read_state(self) -> ReleaseState | None:
        """:return: ``None`` if there is no state (nothing installed with the launcher yet)."""
        data = _read_json(self._releases_dir / self.STATE_FILE)
        return ReleaseState.from_json(data) if data is not None else None

    def staged(self) -> Version | None:
        data = _read_json(self._releases_dir / self.STAGED_FILE)
        if data is None:
            return None
        try:
            return Version(data['version'])
        except (KeyError, TypeError, InvalidVersion) as e:
            raise ValueError(f'Invalid staged release: {data!r}.') from e

    def stage(self, version: Version) -> None:
        """Mark installed ``version`` as the release to switch to on ``ExitCodes.UPDATE``."""
        if not self.is_release_installed(version):
            raise ValueError(f'Release {version} is not installed.')
        write_json_atomic(
            self._releases_dir / self.STAGED_FILE,
            {'schema': RELEASES_SCHEMA, 'version': str(version)},
        )

    def unstage(self) -> None:
        (self._releases_dir / self.STAGED_FILE).unlink(missing_ok=True)

    def pop_result(self) -> UpdateResult | None:
        """Read and remove the result of the last release switch."""
        path = self._releases_dir / self.RESULT_FILE
        try:
            data = _read_json(path)
            return UpdateResult.from_json(data) if data is not None else None
        finally:
            path.unlink(missing_ok=True)


def runtime_python(runtime_dir: Path) -> Path:
    """Interpreter of an installed runtime."""
    if sys.platform == 'win32':
        return runtime_dir / 'python' / 'python.exe'
    return runtime_dir / 'python' / 'bin' / 'python3'


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def write_json_atomic(path: Path, data: Any) -> None:
    temp = path.with_name(f'{path.name}.{secrets.token_hex(8)}.tmp')
    try:
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        replace_with_retry(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def replace_with_retry(src: Path, dst: Path) -> None:
    """``os.replace`` that retries on ``PermissionError``.

    On Windows antivirus, indexer or OneDrive may hold a handle on a just written file
    for a moment.
    """
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_DELAY)
