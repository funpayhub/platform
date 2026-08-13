from __future__ import annotations


__all__ = ['Dispatcher']


from typing import Any
from collections.abc import Callable

from aiogram import Dispatcher as AiogramDispatcher
from aiogram.types import CallbackQuery
from aiogram.fsm.strategy import FSMStrategy
from aiogram.fsm.storage.base import BaseStorage, BaseEventIsolation

from hubplatform.exceptions import BadHashError
from hubplatform.exceptions.telegram import CallbackDataUnpackError
from hubplatform.telegram.callback_data import parse_callback_data
from hubplatform.telegram.callback_data.hash.service import HashService, global_hash_service

from .router import Router


async def parse_callback_data_middleware(
    handler: Callable[..., Any],
    event: CallbackQuery,
    data: dict[str, Any],
) -> Any:
    hash_service: HashService | None = data.get('hash_service')
    if hash_service is None:
        return None  # todo: Error event?

    if event.data is None:
        return None

    if hash_service.is_hash(event.data):
        try:
            unhashed = hash_service.unhash(event.data).query
            object.__setattr__(event, 'data', unhashed)
        except BadHashError:
            return None  # todo: Error event?

    try:
        parse_callback_data(event)
    except CallbackDataUnpackError:
        return None  # todo: Error event?

    return await handler(event, data)


class Dispatcher(AiogramDispatcher, Router):
    def __init__(
        self,
        *,  # * - Preventing to pass instance of Bot to the FSM storage
        storage: BaseStorage | None = None,
        fsm_strategy: FSMStrategy = FSMStrategy.USER_IN_CHAT,
        events_isolation: BaseEventIsolation | None = None,
        disable_fsm: bool = False,
        name: str | None = None,
        hash_service: HashService | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            storage=storage,
            fsm_strategy=fsm_strategy,
            events_isolation=events_isolation,
            disable_fsm=disable_fsm,
            name=name,
            hash_service=hash_service if hash_service is not None else global_hash_service(),
            **kwargs,
        )

        self.callback_query.outer_middleware(parse_callback_data_middleware)  # type: ignore[arg-type]
