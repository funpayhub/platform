from __future__ import annotations

__all__ = ['HubPlatformApp']

from packaging.version import Version
from pyconfigtree import Properties

from hubplatform.app.environment import app_environment, AppEnvironment
from hubplatform.expressions.registry import ExpressionsRegistry, global_expressions_registry
from hubplatform.goods_source import GoodsSourcesManager, global_sources_manager


class HubPlatformApp:
    def __init__(
        self,
        version: Version | str,
        properties: Properties,
        *,
        goods_manager: GoodsSourcesManager = global_sources_manager(),
        expressions_registry: ExpressionsRegistry = global_expressions_registry(),
    ):
        self._version = version if isinstance(version, Version) else Version(version)
        self._properties = properties
        self._goods_manager = goods_manager
        self._expressions_registry = expressions_registry
        self._env = app_environment()

    @property
    def version(self) -> Version:
        return self._version

    @property
    def properties(self) -> Properties:
        return self._properties

    @property
    def goods_manager(self) -> GoodsSourcesManager:
        return self._goods_manager

    @property
    def expressions_registry(self) -> ExpressionsRegistry:
        return self._expressions_registry

    @property
    def environment(self) -> AppEnvironment:
        return self._env

    async def run(self) -> int:
        ...

    async def stop(self) -> None:
        ...

