from __future__ import annotations


__all__ = [
    'finish_input',
    'abort_input',
]

from contextlib import suppress

from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from hubplatform.telegram.ui import UIManager


async def finish_input(
    m: Message,
    state: FSMContext,
    ui_manager: UIManager,
    return_session_id: str,
    input_session_id: str,
) -> None:
    await state.clear()
    with suppress(Exception):
        await ui_manager.close_session(input_session_id, trigger=m)

    try:
        await ui_manager.clone_session(return_session_id, environment=m)
    except Exception:
        await m.answer('Операция выполнена.')


async def abort_input(
    m: Message,
    state: FSMContext,
    ui_manager: UIManager,
    input_session_id: str,
    abort_message: str | None = None,
) -> None:
    await state.clear()
    with suppress(Exception):
        await ui_manager.close_session(input_session_id, trigger=m)

    if abort_message:
        await m.answer(abort_message)
