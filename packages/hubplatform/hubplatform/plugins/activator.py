from __future__ import annotations


__all__ = ['CallbackPluginActivator', 'PluginActivator']


from typing import TypeVar, Protocol
from collections.abc import Callable, Awaitable

from .types import LoadedPlugin


PluginT = TypeVar('PluginT')
AppT_contra = TypeVar('AppT_contra', contravariant=True)


class PluginActivator(Protocol[PluginT, AppT_contra]):
    """Application-specific strategy that binds a loaded plugin to an app."""

    async def activate(
        self,
        plugin: LoadedPlugin[PluginT],
        app: AppT_contra,
    ) -> None: ...


class CallbackPluginActivator(PluginActivator[PluginT, AppT_contra]):
    def __init__(
        self,
        callback: Callable[
            [LoadedPlugin[PluginT], AppT_contra],
            Awaitable[None],
        ],
    ) -> None:
        self._callback = callback

    async def activate(
        self,
        plugin: LoadedPlugin[PluginT],
        app: AppT_contra,
    ) -> None:
        await self._callback(plugin, app)
