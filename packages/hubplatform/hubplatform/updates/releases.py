from __future__ import annotations


__all__ = [
    'RELEASES_SCHEMA',
    'ReleaseManifest',
    'LauncherState',
    'UpdateResult',
    'Releases',
    'write_json_atomic',
]

import os
import json
import time
import shutil
import secrets
import tomllib
from typing import Any, Literal, ClassVar, Annotated
from pathlib import Path

from pydantic import Field, BaseModel, ConfigDict, BeforeValidator, PlainSerializer
from packaging.version import Version, InvalidVersion


RELEASES_SCHEMA = 1
"""Version of the files format."""


_REPLACE_ATTEMPTS = 10
_REPLACE_DELAY = 0.5
VERSION_TYPE = Annotated[
    Version,
    BeforeValidator(lambda v: v if isinstance(v, Version) else Version(v)),
    PlainSerializer(lambda v: str(v), return_type=str, when_used='json-unless-none'),
]


class ReleaseManifest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    version: VERSION_TYPE
    entrypoint: str
    launcher_protocol: int
    FILENAME: ClassVar[str] = 'pyproject.toml'

    def model_post_init(self, context: Any, /) -> None:
        entry_path = Path(self.entrypoint)
        if entry_path.is_absolute() or '..' in entry_path.parts:
            raise ValueError('Invalid entry point.')

    @classmethod
    def from_pyproject(cls, path: Path | str) -> ReleaseManifest:
        path = Path(path)
        if not path.parts[-1] == cls.FILENAME:
            path = path / cls.FILENAME
        try:
            with path.open('rb') as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            raise ValueError(f'Release has no {cls.FILENAME}.') from None
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f'Release {cls.FILENAME} is invalid: {e}.') from e

        release = data.get('tool', {}).get('hubplatform', {}).get('release', {})
        manifest = ReleaseManifest(
            version=data.get('project', {}).get('version'),
            entrypoint=release.get('entrypoint', 'app.py'),
            launcher_protocol=release.get('launcher-protocol', 1),
        )

        if not (path.with_name(manifest.entrypoint)).is_file():
            raise ValueError(f'Release entrypoint {manifest.entrypoint!r} does not exist.')
        return manifest


class LauncherState(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    current_version: VERSION_TYPE
    is_pending: bool = False
    run_attempts: int = 0
    previous_version: VERSION_TYPE | None = None
    failed_rallbacks: tuple[VERSION_TYPE, ...] = ()


class UpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    status: Literal['updated', 'rolled_back', 'failed']
    version: VERSION_TYPE
    previous: VERSION_TYPE | None = None
    message: str | None = None


class UpdateInfo(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    schema: int = Field(default=1, lt=2, gt=0)
    version: VERSION_TYPE


class InstalledMarker(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    schema: int = Field(default=1, lt=2, gt=0)
    version: VERSION_TYPE
    sha256: str | None = None
    installed_at: int = Field(default_factory=lambda: int(time.time()))


class Releases:
    """Access to a releases directory from the app."""

    LAUNCHER_STATE_FILE = '.launcher_state'
    UPDATE_INFO_FILE = '.update_info'
    UPDATE_RESULT_FILE = '.update_result'
    DOWNLOADS_DIR = '.downloads'
    MARKER_FILE = '.installed'
    VENV_DIR = '.venv'
    TEMP_PREFIX = '.tmp-'

    def __init__(self, path: str | Path = './releases') -> None:
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
        result: list[Version] = []
        if not self._path.is_dir():
            return ()
        for i in self._path.iterdir():
            if self.is_version_name(i) and self.is_installed(Version(i.name)):
                result.append(Version(i.name))
        return tuple(sorted(result, reverse=True))

    def mark_installed(self, version: Version, sha256: str | None) -> None:
        write_json_atomic(
            self.release_dir(version) / self.MARKER_FILE,
            InstalledMarker(version=version, sha256=sha256).model_dump(mode='json'),
        )

    def temp_dir(self, version: Version) -> Path:
        return self._path / f'{self.TEMP_PREFIX}{version}-{secrets.token_hex(8)}'

    def get_launcher_state(self) -> LauncherState | None:
        data = _read_json(self._path / self.LAUNCHER_STATE_FILE)
        return None if data is None else LauncherState.model_validate(data)

    def get_update_info(self) -> UpdateInfo | None:
        data = _read_json(self._path / self.UPDATE_INFO_FILE)
        if data is None:
            return None
        try:
            return UpdateInfo.model_validate(data)
        except Exception:
            return None

    def mark_to_update(self, version: Version) -> None:
        if not self.is_installed(version):
            raise ValueError(f'Release {version} is not installed.')
        write_json_atomic(
            self._path / self.UPDATE_INFO_FILE, UpdateInfo(version=version).model_dump(mode='json')
        )

    def unmark_to_update(self) -> None:
        (self._path / self.UPDATE_INFO_FILE).unlink(missing_ok=True)

    def pop_update_result(self) -> UpdateResult | None:
        path = self._path / self.UPDATE_RESULT_FILE
        try:
            data = _read_json(path)
            return None if data is None else UpdateResult.model_validate(data)
        finally:
            path.unlink(missing_ok=True)

    def remove_leftovers(self) -> None:
        if not self.path.is_dir():
            return
        for i in self.path.iterdir():
            if i.is_symlink() or i.is_junction() or not i.is_dir():
                continue
            if i.name.startswith(self.TEMP_PREFIX) or (
                self.is_version_name(i) and not (i / self.MARKER_FILE).exists()
            ):
                shutil.rmtree(i, ignore_errors=True)

    @classmethod
    def is_version_name(cls, name: str | Path) -> bool:
        if isinstance(name, Path):
            name = name.name

        try:
            return str(Version(name)) == name
        except InvalidVersion:
            return False


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def write_json_atomic(path: Path, data: Any) -> None:
    temp = path.with_name(f'{path.name}.{secrets.token_hex(8)}.tmp')
    try:
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        replace_with_retry(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def replace_with_retry(src: Path, dst: Path) -> None:
    # Windows defender / OneDrive / other staff can hold a handle to path for some time.
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_DELAY)
