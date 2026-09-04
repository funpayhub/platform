from __future__ import annotations


__all__ = ['Dispatcher']

from typing import Any
from collections.abc import Mapping

from eventry.asyncio import Router, Dispatcher as BaseDispatcher, DispatchingConfig


class Dispatcher(BaseDispatcher):
    def __init__(
        self,
        router: Router[Any] | None = None,
        event_context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(router=router, event_context=event_context, config=DispatchingConfig())
