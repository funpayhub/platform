from __future__ import annotations


__all__ = ['HubPlatformApp']

from collections.abc import Sequence, Mapping

from pyconfigtree import Properties
from packaging.version import Version

from hubplatform.goods_source import GoodsSourcesManager, global_sources_manager
from hubplatform.app.environment import AppEnvironment, app_environment
from hubplatform.expressions.registry import ExpressionsRegistry, global_expressions_registry
from types import MappingProxyType
import asyncio
from .app_component import HubPlatformAppComponent
from hubplatform.app_context import AppContext


class HubPlatformApp:
    def __init__(
        self,
        version: Version | str,
        properties: Properties,
        *,
        goods_manager: GoodsSourcesManager = global_sources_manager(),
        expressions_registry: ExpressionsRegistry = global_expressions_registry(),
        components: Sequence[HubPlatformAppComponent] = (),
    ):
        self._version = version if isinstance(version, Version) else Version(version)
        self._properties = properties

        self._components: dict[str, HubPlatformAppComponent] = {}
        for component in components:
            if component.component_name in self._components:
                raise RuntimeError(f'Component {component.component_name} already added.')
            self._components[component.component_name] = component

        self._goods_manager = goods_manager
        self._expressions_registry = expressions_registry
        self._app_context = AppContext()
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

    @property
    def app_context(self) -> AppContext:
        return self._app_context

    @property
    def components(self) -> Mapping[str, HubPlatformAppComponent]:
        return MappingProxyType(self._components)

    async def setup(self) -> None:
        for component in self._components.values():
            await component.setup_context(self._app_context)

    async def run(self) -> None:
        tasks = [component.run() for component in self._components.values()]
        finished, pending = await asyncio.wait(*tasks)

    def stop(self) -> None: ...
