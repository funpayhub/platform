from __future__ import annotations


__all__ = ['PluginsRepository']


from abc import ABC, abstractmethod

from packaging.version import Version

from .types import PluginDetails, RepositoryPage


class PluginsRepository(ABC):
    @property
    @abstractmethod
    def repository_id(self) -> str:
        """Return a stable identifier used to distinguish plugin repositories."""

        ...

    @abstractmethod
    async def get_plugins(
        self,
        app_version: Version,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> RepositoryPage:
        """Return plugins compatible with the supplied application version."""

        ...

    @abstractmethod
    async def get_plugin(
        self,
        plugin_id: str,
        app_version: Version | None = None,
    ) -> PluginDetails:
        """Return plugin metadata, optionally filtered by application version."""

        ...
