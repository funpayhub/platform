from __future__ import annotations

__all__ = ['HubPlatformApp']

from packaging.version import Version
from pyconfigtree import Properties

from hubplatform.app.environment import app_environment, AppEnvironment
from hubplatform.goods_source import GoodsSourcesManager


class HubPlatformApp:
    def __init__(
        self,
        version: Version | str,
        properties: Properties,
        *,
        goods_manager: GoodsSourcesManager | None = None,
    ):
        self._version = version if isinstance(version, Version) else Version(version)
        self._properties = properties
        self._goods_manager = goods_manager if goods_manager is not None else GoodsSourcesManager()
        self._env = app_environment()

    @property
    def properties(self) -> Properties:
        return self._properties

    @property
    def goods_manager(self) -> GoodsSourcesManager:
        return self._goods_manager

    @property
    def environment(self) -> AppEnvironment:
        return self._env

    async def start(self) -> int:
        ...

    async def stop(self) -> None:
        ...

