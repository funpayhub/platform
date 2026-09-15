from __future__ import annotations


__all__ = ['VersionsManager']


from abc import ABC, abstractmethod
from pathlib import Path

from packaging.version import Version

from ..types import AppVersionInfo


class VersionsManager(ABC):
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
    async def download_version(
        self, version: Version | str | AppVersionInfo, path: str | Path | None = None
    ) -> Path:
        pass

    def _to_version(self, version: Version | str | AppVersionInfo) -> Version:
        if isinstance(version, Version):
            return version
        if isinstance(version, str):
            return Version(version)
        if isinstance(version, AppVersionInfo):
            return version.version
        raise TypeError(f'Can not convert {version} to version.')
