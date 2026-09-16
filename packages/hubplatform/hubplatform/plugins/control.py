from __future__ import annotations


__all__ = ['PluginControl', 'PluginStateListener']


from typing import Protocol
from collections.abc import Mapping, Callable, Awaitable

from packaging.version import Version

from .types import PluginSnapshot, PluginOperationResult
from .installer import PluginArtifact
from .repository.base import PluginsRepository


PluginStateListener = Callable[
    [Mapping[str, PluginSnapshot]],
    Awaitable[None] | None,
]


class PluginControl(Protocol):
    """Narrow API exposed to the application and its management UI."""

    @property
    def snapshots(self) -> Mapping[str, PluginSnapshot]: ...

    @property
    def repositories(self) -> Mapping[str, PluginsRepository]: ...

    def subscribe(self, listener: PluginStateListener) -> Callable[[], None]: ...

    async def install(
        self,
        artifact: PluginArtifact,
        *,
        enable: bool = True,
    ) -> PluginOperationResult: ...

    async def install_from_repository(
        self,
        repository_id: str,
        plugin_id: str,
        plugin_version: Version | str | None = None,
        *,
        enable: bool = True,
    ) -> PluginOperationResult: ...

    async def enable(self, plugin_id: str) -> PluginOperationResult: ...

    async def disable(
        self,
        plugin_id: str,
        *,
        cascade: bool = False,
    ) -> PluginOperationResult: ...

    async def uninstall(
        self,
        plugin_id: str,
        *,
        cascade: bool = False,
    ) -> PluginOperationResult: ...
