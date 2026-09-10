from __future__ import annotations


__all__ = ['RestrictedCallbackQueryObserver']

from typing import Any

from aiogram.filters.callback_data import CallbackQueryFilter as AiogramCallbackQueryFilter
from aiogram.dispatcher.event.handler import CallbackType
from aiogram.dispatcher.event.telegram import TelegramEventObserver


def _check_filter_type(filter_: Any) -> None:
    if isinstance(filter_, AiogramCallbackQueryFilter):
        raise TypeError(
            '`aiogram.filters.callback_data.CallbackQueryFilter` '
            'is not supported by Hub Platform. '
            'Use `hubplatform.telegram.callback_data.CallbackQueryFilter` instead. '
            "If the filter was created via aiogram's `CallbackData.filter()`, "
            'use `hubplatform.telegram.callback_data.CallbackData.filter()` instead.'
        )


class RestrictedCallbackQueryObserver(TelegramEventObserver):
    def filter(self, *filters: CallbackType) -> None:
        for filter_ in filters:
            _check_filter_type(filter_)
        return super().filter(*filters)

    def register(
        self,
        callback: CallbackType,
        *filters: CallbackType,
        flags: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> CallbackType:
        for f in filters:
            _check_filter_type(f)

        return super().register(callback, *filters, flags=flags, **kwargs)
