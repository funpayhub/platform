from __future__ import annotations


__all__ = [
    'PluginInjector',
]

from typing import TYPE_CHECKING
from collections.abc import Sequence

from hubplatform.plugins.loader import LoadedPlugin


if TYPE_CHECKING:
    from hubplatform.app import HubPlatformApp


class PluginInjector:
    def __init__(self, plugins: Sequence[LoadedPlugin]) -> None:
        self._plugins = tuple(plugins)

    @property
    def plugins(self) -> tuple[LoadedPlugin, ...]:
        return self._plugins

    async def install_plugins(self, app: HubPlatformApp) -> None:
        for plugin in self._plugins:
            await plugin.plugin_instance.install(app)
