from __future__ import annotations


__all__ = ['Router']

from typing import Any
from collections.abc import Callable

from eventry.asyncio import (
    Router as EventryRouter,
    Context,
    FromContext,
    RouterConfig,
    MiddlewareStorage,
    DefaultHandlerManager,
)

from .event import NodeAttachedEvent, NodeDetachedEvent, ParameterValueChangedEvent


class Router(EventryRouter[Callable[..., Any]]):
    def __init__(self, name: str = '') -> None:
        super().__init__(
            name=name,
            config=RouterConfig(
                outer_mdw_args=(FromContext('next_call'), Context),
                inner_mdw_args=(FromContext('next_call'), Context),
            ),
        )

        self.middleware['router.outer'] = MiddlewareStorage()
        self.middleware['router.inner'] = MiddlewareStorage()

        self.on_parameter_value_changed = self.add_handler_manager(
            DefaultHandlerManager(
                'on_parameter_value_changed',
                ParameterValueChangedEvent.__event_name__,
            )
        )

        self.on_node_attached = self.add_handler_manager(
            DefaultHandlerManager(
                'on_node_attached',
                NodeAttachedEvent.__event_name__,
            )
        )

        self.on_node_detached = self.add_handler_manager(
            DefaultHandlerManager(
                'on_node_detached',
                NodeDetachedEvent.__event_name__,
            )
        )

    @property
    def outer_middleware(self) -> MiddlewareStorage:
        return self.middleware['router.outer']

    @property
    def inner_middleware(self) -> MiddlewareStorage:
        return self.middleware['router.inner']
