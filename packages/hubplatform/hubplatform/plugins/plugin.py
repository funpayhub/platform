from __future__ import annotations


__all__ = [
    'HubPlatformPlugin',
    'HubPlatformPluginProto',
]


from typing import TYPE_CHECKING, Protocol, runtime_checkable
from abc import ABC


if TYPE_CHECKING:
    from hubplatform.app import HubPlatformApp


@runtime_checkable
class HubPlatformPluginProto(Protocol):
    async def install(self, app: HubPlatformApp) -> None:
        pass


class HubPlatformPlugin(ABC, HubPlatformPluginProto):
    async def install(self, app: HubPlatformApp) -> None:
        raise NotImplementedError
