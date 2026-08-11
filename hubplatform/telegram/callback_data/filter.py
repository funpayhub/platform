from __future__ import annotations


__all__ = [
    'CallbackQueryFilter',
]

from typing import Any, Literal

from aiogram.types import CallbackQuery
from aiogram.filters import Filter

from hubplatform.exceptions.telegram import CallbackIdentifierMismatchError
from hubplatform.telegram.callback_data.hash import HashService

from .models import CallbackData, parse_callback_data


class CallbackQueryFilter(Filter):
    """Parse a callback query and validate it as a concrete callback model."""

    def __init__(self, *, callback_data: type[CallbackData]) -> None:
        self.callback_data = callback_data

    async def __call__(
        self, query: CallbackQuery | str, hash_service: HashService
    ) -> Literal[False] | dict[str, Any]:
        if not isinstance(query, (CallbackQuery, str)):
            return False

        try:
            envelope = parse_callback_data(query)

            if envelope.identifier != self.callback_data.identifier:
                return False

            callback_data = self.callback_data.from_envelope(envelope)
        except CallbackIdentifierMismatchError:
            return False

        return {'callback_data': callback_data, 'cbd': callback_data}
