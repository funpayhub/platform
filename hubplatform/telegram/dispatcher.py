from __future__ import annotations


__all__ = ['Dispatcher']


from typing import Any
from collections.abc import Callable

from aiogram import Dispatcher as AiogramDispatcher
from aiogram.types import CallbackQuery
from exceptions.telegram import CallbackDataUnpackError
from aiogram.fsm.strategy import FSMStrategy
from aiogram.fsm.storage.base import BaseStorage, BaseEventIsolation

from hubplatform.exceptions import BadHashError
from hubplatform.telegram.callback_data import parse_callback_data
from hubplatform.telegram.callback_data.hash import HashService


async def parse_callback_data_middleware(
    event: CallbackQuery, handler: Callable[..., Any], data: dict[str, Any]
) -> Any:
    hash_service: HashService | None = data.get('hash_service')
    if hash_service is None:
        return None  # todo: Error event?

    to_parse = event
    if hash_service.is_hash(event.data):
        try:
            to_parse = hash_service.unhash(event.data).query
        except BadHashError:
            return None  # todo: Error event?

    try:
        parse_callback_data(to_parse)
    except CallbackDataUnpackError:
        return None  # todo: Error event?

    return await handler(event, data)


class Dispatcher(AiogramDispatcher):
    def __init__(
        self,
        *,  # * - Preventing to pass instance of Bot to the FSM storage
        storage: BaseStorage | None = None,
        fsm_strategy: FSMStrategy = FSMStrategy.USER_IN_CHAT,
        events_isolation: BaseEventIsolation | None = None,
        disable_fsm: bool = False,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            storage=storage,
            fsm_strategy=fsm_strategy,
            events_isolation=events_isolation,
            disable_fsm=disable_fsm,
            name=name,
            **kwargs,
        )

        self.callback_query.outer_middleware(parse_callback_data_middleware)
