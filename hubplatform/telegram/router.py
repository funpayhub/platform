from __future__ import annotations


__all__ = ['Router']


from typing import Any

from aiogram import Router as AiogramRouter

from ._restricted_aiogram_observers import RestrictedCallbackQueryObserver


def _check_router_type(router: Any) -> None:
    if not isinstance(router, Router):
        raise TypeError(
            '`aiogram.Router` is not supported by Hub Platform. '
            'Use `hubplatform.telegram.Router` instead. '
        )


class Router(AiogramRouter):
    def __init__(self, *, name: str | None = None) -> None:
        super().__init__(name=name)

        self.callback_query = RestrictedCallbackQueryObserver(
            router=self, event_name='callback_query'
        )
        self.observers['callback_query'] = self.callback_query

    def include_router(self, router: AiogramRouter) -> Router:
        _check_router_type(router)
        return super().include_router(router)
