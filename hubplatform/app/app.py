from __future__ import annotations


__all__ = ['HubPlatformApp']

import asyncio
from enum import Enum, auto
from typing import Any
from types import MappingProxyType
from collections.abc import Mapping, Sequence

from pyconfigtree import Node, Properties, MutableParameter
from packaging.version import Version
from pyconfigtree.parameter.base import ParameterHookTypes

from hubplatform.app_context import AppContext
from hubplatform.goods_source import GoodsSourcesManager, global_sources_manager
from hubplatform.app.environment import AppEnvironment, app_environment
from hubplatform.expressions.registry import ExpressionsRegistry, global_expressions_registry

from .dispatching import (
    Router,
    Dispatcher,
    NodeAttachedEvent,
    NodeDetachedEvent,
    ParameterValueChangedEvent,
)
from .app_component import HubPlatformAppComponent


class AppState(Enum):
    INITIALIZED = auto()
    SETTING_UP = auto()
    READY = auto()
    RUNNING = auto()
    STOPPING = auto()


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
        self._router = Router(name='HubPlatformApp')
        self._dispatcher = Dispatcher(router=self._router, event_context=self._app_context)

        self._properties.on_node_attached_hook = self._on_node_attached_hook
        self._properties.on_node_detached_hook = self._on_node_detached_hook
        self._properties._hooks[ParameterHookTypes.PARAMETER_VALUE_CHANGED] = (
            self._on_parameter_value_changed_hook
        )

        self._state = AppState.INITIALIZED

    async def _on_node_attached_hook(self, attached_node: Node, attached_to: Node) -> None:
        event = NodeAttachedEvent(attached_node=attached_node, attached_to=attached_to)
        await self._dispatcher.propagate_event(event)

    async def _on_node_detached_hook(self, detached_node: Node, detached_from: Node) -> None:
        event = NodeDetachedEvent(detached_node=detached_node, detached_from=detached_from)
        await self._dispatcher.propagate_event(event)

    async def _on_parameter_value_changed_hook(self, parameter: MutableParameter[Any]) -> None:
        event = ParameterValueChangedEvent(parameter=parameter)
        await self._dispatcher.propagate_event(event)

    def _check_state(self, state: AppState) -> None:
        if self._state is not state:
            raise RuntimeError(
                f'This operation requires app state {state}, but current state is {self._state}'
            )

    @property
    def state(self) -> AppState:
        return self._state

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
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    @property
    def router(self) -> Router:
        return self._router

    @property
    def components(self) -> Mapping[str, HubPlatformAppComponent]:
        return MappingProxyType(self._components)

    async def setup(self) -> None:
        self._check_state(AppState.INITIALIZED)
        self._state = AppState.SETTING_UP

        for component in self._components.values():
            await component.setup_context(self._app_context)

        self._state = AppState.READY

    async def run(self) -> None:
        self._check_state(AppState.READY)

        tasks = [component.run() for component in self._components.values()]

        self._state = AppState.RUNNING
        finished, pending = await asyncio.wait(*tasks)

        self._state = AppState.READY

    def stop(self) -> None: ...
