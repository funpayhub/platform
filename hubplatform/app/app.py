from __future__ import annotations


__all__ = ['HubPlatformApp']

import asyncio
from typing import Any
from enum import Enum, auto
from types import MappingProxyType
from collections.abc import Mapping, Sequence

from pyconfigtree import Node, Properties, MutableParameter
from packaging.version import Version
from pyconfigtree.parameter.base import ParameterHookTypes

from hubplatform.app_context import AppContext
from hubplatform.goods_source import GoodsSourcesManager, global_sources_manager
from hubplatform.app.environment import AppEnvironment, app_environment
from hubplatform.logging.loggers import app
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
        self._stop_signal = asyncio.Event()
        self._stopped_signal = asyncio.Event()

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
        self._stop_signal.clear()
        self._stopped_signal.clear()

        tasks: set[asyncio.Task[Any]] = {
            asyncio.create_task(component.run(), name=component.component_name)
            for component in self._components.values()
        }
        stop_task = asyncio.create_task(self._stop_signal.wait(), name='HubPlatformApp.StopSignal')
        tasks.add(stop_task)

        self._state = AppState.RUNNING
        to_wait: set[asyncio.Task[Any]] = tasks
        while True:
            done, pending = await asyncio.wait(to_wait, return_when=asyncio.FIRST_COMPLETED)

            if not self._stop_signal.is_set():
                _process_done(done, stop_task)
                to_wait = pending
                continue
            break

        app.main.info('Stopping the app...')
        _process_done(done, stop_task)
        for i in pending:
            try:
                self._components[i.get_name()].stop()
            except Exception as e:
                app.main.error(
                    'An unexpected error occurred while sending stop request to component %s. '
                    'Cancelling it...',
                    i.get_name(),
                    exc_info=e,
                )
                i.cancel()

        done, pending = await asyncio.wait(pending, timeout=30)
        _process_done(done, stop_task)

        for i in pending:
            app.main.warning(
                "Component %s hasn't been stopped in 30 seconds. Cancelling it ...", i.get_name()
            )
            i.cancel()

        done, pending = await asyncio.wait(pending, timeout=30)
        _process_done(done, stop_task)
        for i in pending:
            app.main.error("Component %s hasn't been cancelled in 30 seconds.", i.get_name())
            # todo: return AppStopState(
            #       stopped_components: set[component],
            #       errored_components: set[component],
            #       not_responding: set[component],
            #   )

        self._stopped_signal.set()
        self._state = AppState.READY
        return

    def stop(self) -> None:
        self._check_state(state=AppState.RUNNING)
        self._state = AppState.STOPPING
        self._stop_signal.set()

    async def wait_stopped(self) -> None:
        await self._stopped_signal.wait()


def _process_done(done: set[asyncio.Task[Any]], stop_task: asyncio.Task[Any]) -> None:
    for i in done:
        if i is stop_task:
            continue

        try:
            i.result()
        except asyncio.CancelledError:
            app.main.warning('Component %s has been unexpectedly cancelled.', i.get_name())
        except NotImplementedError:
            app.main.info('Component %s does not implement long-live service.', i.get_name())
        except Exception as e:
            app.main.error('Component %s has been unexpectedly failed.', i.get_name(), exc_info=e)
        else:
            app.main.info('Component %s has been stopped.', i.get_name())
