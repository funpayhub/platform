"""Releases directory: the file part of the launcher protocol (see :mod:`hubplatform.runtime`).

Layout::

    releases/
        1.3.2/              installed release: sources, pyproject.toml, .venv/, .installed
        1.4.0/
        .downloads/         downloaded archives (app)
        state.json          current / previous release (written by the launcher only)
        staged.json         release to switch to on ExitCodes.UPDATE (written by the app only)
        result.json         outcome of the last switch (launcher writes, app removes)

A release directory is complete only when its ``.installed`` marker exists; anything else
in ``releases/`` is a leftover of an interrupted installation and may be removed.

Each file has a single writer, so the app and the launcher never write the same file.
All files are written atomically (temporary file + rename).
"""

from __future__ import annotations


__all__ = [
    'RELEASES_SCHEMA',
    'ReleaseManifest',
    'ReleaseState',
    'UpdateResult',
    'Releases',
    'write_json_atomic',
]

import os
import json
import time
import secrets
import tomllib
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
class ReleaseManifest:
    """Release metadata, read from the release ``pyproject.toml``.

    .. code-block:: toml

        [project]
        version = "1.4.0"

        [tool.hubplatform.release]
        entrypoint = "app.py"     # optional, default: app.py
        launcher-protocol = 1     # optional, minimal launcher protocol, default: 1
    """

    version: Version
    entrypoint: str
    launcher_protocol: int

    FILENAME = 'pyproject.toml'

    @classmethod
    def read(cls, release_dir: Path) -> ReleaseManifest:
        """:raises ValueError: the manifest is missing or invalid."""
        path = release_dir / cls.FILENAME
        try:
            with path.open('rb') as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            raise ValueError(f'Release has no {cls.FILENAME}.') from None
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f'Release {cls.FILENAME} is invalid: {e}.') from e

        try:
            version = Version(data['project']['version'])
        except (KeyError, TypeError, InvalidVersion) as e:
            raise ValueError(f'Release {cls.FILENAME} has no valid project.version.') from e

        release = data.get('tool', {}).get('hubplatform', {}).get('release', {})
        entrypoint = release.get('entrypoint', 'app.py')
        protocol = release.get('launcher-protocol', 1)
        if (
            not isinstance(entrypoint, str)
            or Path(entrypoint).is_absolute()
            or '..' in Path(entrypoint).parts
        ):
            raise ValueError(f'Invalid release entrypoint: {entrypoint!r}.')
        if not (release_dir / entrypoint).is_file():
            raise ValueError(f'Release entrypoint {entrypoint!r} does not exist.')
        if not isinstance(protocol, int) or isinstance(protocol, bool):
            raise ValueError(f'Invalid release launcher-protocol: {protocol!r}.')

        return cls(version=version, entrypoint=entrypoint, launcher_protocol=protocol)


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


class Releases:
    """Access to a releases directory from the app."""

    STATE_FILE = 'state.json'
    STAGED_FILE = 'staged.json'
    RESULT_FILE = 'result.json'
    DOWNLOADS_DIR = '.downloads'
    MARKER_FILE = '.installed'
    VENV_DIR = '.venv'
    TEMP_PREFIX = '.tmp-'

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser().resolve()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def downloads_dir(self) -> Path:
        return self._path / self.DOWNLOADS_DIR

    def release_dir(self, version: Version) -> Path:
        return self._path / str(version)

    def venv_dir(self, version: Version) -> Path:
        return self.release_dir(version) / self.VENV_DIR

    def is_installed(self, version: Version) -> bool:
        return (self.release_dir(version) / self.MARKER_FILE).is_file()

    def installed(self) -> tuple[Version, ...]:
        """Installed releases, newest first."""
        result: list[Version] = []
        if not self._path.is_dir():
            return ()
        for i in self._path.iterdir():
            try:
                version = Version(i.name)
            except InvalidVersion:
                continue
            if str(version) == i.name and self.is_installed(version):
                result.append(version)
        return tuple(sorted(result, reverse=True))

    def mark_installed(self, version: Version, sha256: str | None) -> None:
        write_json_atomic(
            self.release_dir(version) / self.MARKER_FILE,
            {
                'schema': RELEASES_SCHEMA,
                'version': str(version),
                'sha256': sha256,
                'installed_at': datetime.now(UTC).isoformat(),
            },
        )

    def temp_dir(self, version: Version) -> Path:
        """New unique directory name for unpacking ``version``."""
        return self._path / f'{self.TEMP_PREFIX}{version}-{secrets.token_hex(8)}'

    def read_state(self) -> ReleaseState | None:
        """:return: ``None`` if there is no state (nothing installed with the launcher yet)."""
        data = _read_json(self._path / self.STATE_FILE)
        return ReleaseState.from_json(data) if data is not None else None

    def staged(self) -> Version | None:
        data = _read_json(self._path / self.STAGED_FILE)
        if data is None:
            return None
        try:
            return Version(data['version'])
        except (KeyError, TypeError, InvalidVersion) as e:
            raise ValueError(f'Invalid staged release: {data!r}.') from e

    def stage(self, version: Version) -> None:
        """Mark installed ``version`` as the release to switch to on ``ExitCodes.UPDATE``."""
        if not self.is_installed(version):
            raise ValueError(f'Release {version} is not installed.')
        write_json_atomic(
            self._path / self.STAGED_FILE,
            {'schema': RELEASES_SCHEMA, 'version': str(version)},
        )

    def unstage(self) -> None:
        (self._path / self.STAGED_FILE).unlink(missing_ok=True)

    def pop_result(self) -> UpdateResult | None:
        """Read and remove the result of the last release switch."""
        path = self._path / self.RESULT_FILE
        try:
            data = _read_json(path)
            return UpdateResult.from_json(data) if data is not None else None
        finally:
            path.unlink(missing_ok=True)


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
