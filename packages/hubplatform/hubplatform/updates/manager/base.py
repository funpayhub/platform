from __future__ import annotations


__all__ = ['VersionsManager', 'DEFAULT_UPDATE_FILENAME']


import os
import string
import asyncio
import secrets
from typing import Self
from dataclasses import field, dataclass
from abc import ABC, abstractmethod
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from packaging.version import Version

from hubplatform.core import convert_exceptions
from hubplatform.updates import exceptions as exc

from ..types import AppVersionInfo


DEFAULT_UPDATE_FILENAME = 'update.zip'
_TEMP_SUFFIX_ALPHABET = string.ascii_letters + string.digits
_TEMP_SUFFIX_LENGTH = 24


@dataclass
class _FileLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


# Download locks shared by all managers, one per destination file.
# An entry is removed as soon as nobody holds or waits for it.
_DOWNLOAD_LOCKS: dict[str, _FileLock] = {}


@asynccontextmanager
async def _lock_file(destination: Path, wait: bool) -> AsyncIterator[None]:
    key = os.path.normcase(destination)
    file_lock = _DOWNLOAD_LOCKS.get(key)
    if file_lock is None:
        file_lock = _DOWNLOAD_LOCKS[key] = _FileLock()

    if not wait and file_lock.lock.locked():
        raise exc.VersionDownloadInProgressError(destination)

    file_lock.users += 1
    try:
        async with file_lock.lock:
            yield
    finally:
        file_lock.users -= 1
        if not file_lock.users:
            del _DOWNLOAD_LOCKS[key]


class VersionsManager(ABC):
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        pass

    @classmethod
    def is_downloading(cls, path: str | Path, filename: str = DEFAULT_UPDATE_FILENAME) -> bool:
        """Whether **any** manager is downloading into ``path / filename`` right now."""
        file_lock = _DOWNLOAD_LOCKS.get(os.path.normcase(cls._destination(path, filename)))
        return file_lock is not None and file_lock.lock.locked()

    @abstractmethod
    async def get_latest_version(self) -> AppVersionInfo:
        pass

    @abstractmethod
    async def get_version_info(self, version: Version | str) -> AppVersionInfo:
        pass

    @abstractmethod
    async def get_versions(self, from_: Version | None = None) -> tuple[Version, ...]:
        pass

    @abstractmethod
    async def _download_file(self, version_info: AppVersionInfo, path: Path) -> None:
        """Download ``version_info`` into ``path``. ``path`` is a temporary file."""

    async def download_version(
        self,
        version: Version | str | AppVersionInfo,
        path: str | Path,
        filename: str = DEFAULT_UPDATE_FILENAME,
        wait: bool = False,
    ) -> Path:
        """Download ``version`` into folder ``path`` as ``filename``.

        The data is first written to ``<filename>.<random suffix>`` in the same folder
        and renamed to ``filename`` only after the download succeeded.

        Only one download into the same file may run at a time, across all managers
        (the lock is held from the start of the temporary download until the rename).
        If one is running, ``wait=True`` waits for it to finish and then downloads again,
        overwriting the file; ``wait=False`` raises immediately.

        :raises VersionDownloadInProgressError: the file is being downloaded and ``wait`` is False.
        :raises NotADirectoryError: ``path`` exists and is not a directory.
        :raises ValueError: ``filename`` is not a plain file name.
        :raises VersionDownloadError: download failed.
        """
        destination = self._destination(path, filename)
        directory = destination.parent
        if directory.exists() and not directory.is_dir():
            raise NotADirectoryError(f'{directory} exists and is not a directory.')

        async with _lock_file(destination, wait):
            directory.mkdir(parents=True, exist_ok=True)

            if isinstance(version, AppVersionInfo):
                version_info = version
            else:
                version_info = await self.get_version_info(version)

            temp_path = directory / f'{filename}.{self._random_suffix()}'
            try:
                async with convert_exceptions(
                    except_=exc.VersionManagerError,
                    exception_factory=lambda: exc.VersionDownloadError(version_info.version),
                ):
                    await self._download_file(version_info, temp_path)
                    temp_path.replace(destination)
            finally:
                temp_path.unlink(missing_ok=True)

            return destination

    @staticmethod
    def _destination(path: str | Path, filename: str) -> Path:
        if not filename or filename in {'.', '..'} or Path(filename).name != filename:
            raise ValueError(f'Invalid file name: {filename!r}.')
        return Path(path).expanduser().resolve() / filename

    @staticmethod
    def _random_suffix() -> str:
        return ''.join(secrets.choice(_TEMP_SUFFIX_ALPHABET) for _ in range(_TEMP_SUFFIX_LENGTH))

    def _to_version(self, version: Version | str | AppVersionInfo) -> Version:
        if isinstance(version, Version):
            return version
        if isinstance(version, str):
            return Version(version)
        if isinstance(version, AppVersionInfo):
            return version.version
        raise TypeError(f'Can not convert {version} to version.')
