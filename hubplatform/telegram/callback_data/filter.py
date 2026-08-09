from __future__ import annotations


__all__ = [
    'CallbackQueryFilter',
]

from typing import Any, Literal

from pydantic import ValidationError
from aiogram.types import CallbackQuery
from aiogram.filters import Filter

from hubplatform.exceptions import BadHashError
from hubplatform.telegram.callback_data.hash import HashService

from .models import CallbackData, ParsedEnvelope


class CallbackQueryFilter(Filter):
    """Parse a callback query and validate it as a concrete callback model."""

    def __init__(
        self,
        *,
        callback_data: type[CallbackData],
        hash_service: HashService | None = None,
    ) -> None:
        self.callback_data = callback_data
        self.hash_service = hash_service

    async def __call__(
        self, query: CallbackQuery | str, hash_service: HashService
    ) -> Literal[False] | dict[str, Any]:
        if not isinstance(query, (CallbackQuery, str)):
            return False

        data = query if isinstance(query, str) else query.data
        if not data:
            return False

        hash_service = self.hash_service if self.hash_service is not None else hash_service

        try:
            envelope: ParsedEnvelope | None = (
                None if isinstance(query, str) else getattr(query, '__callback_envelope__', None)
            )
            if envelope is None:
                envelope = ...  # todo
                if isinstance(query, CallbackQuery):
                    query.__dict__['__callback_envelope__'] = envelope

            if envelope.identifier != self.callback_data.identifier:
                return False

            callback_data = self.callback_data.from_envelope(envelope)
        except (BadHashError, TypeError, ValueError, ValidationError):
            return False

        return {'callback_data': callback_data, 'cbd': callback_data}
