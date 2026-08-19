from __future__ import annotations

from aiogram.types import Message, CallbackQuery as Query
from aiogram.fsm.context import FSMContext

from hubplatform.telegram.router import Router
from hubplatform.telegram.ui.registry import UIRegistry

from . import utils, callbacks as cbs


router = Router(name='hubplatform.ui_router')


@router.callback_query(cbs.OpenMenu.filter())
async def open_menu(q: Query, cbd: cbs.OpenMenu, tg_ui_registry: UIRegistry) -> None:
    await utils.apply_menu_snapshot(
        snapshot=cbd.snapshot,
        target=q,
        ui_registry=tg_ui_registry,
        new_message=cbd.new_message,
    )


@router.callback_query(cbs.ChangePageTo.filter())
async def change_page(q: Query, cbd: cbs.ChangePageTo, tg_ui_registry: UIRegistry) -> None:
    context = tg_ui_registry.context_from_snapshot(cbd.snapshot, runtime=utils.extract_runtime(q))
    if cbd.keyboard_page is not None:
        context.keyboard_page = cbd.keyboard_page
    if cbd.text_page is not None:
        context.text_page = cbd.text_page
    await utils.apply_menu_context(context=context, target=q, ui_registry=tg_ui_registry)


@router.callback_query(cbs.ClearState.filter())
async def clear_state(
    q: Query, cbd: cbs.ClearState, tg_ui_registry: UIRegistry, state: FSMContext
) -> None:
    await state.clear()
    if cbd.mode == 'delete' and isinstance(q.message, Message):
        await q.message.delete()
    elif cbd.mode == 'go_back':
        ctx = tg_ui_registry.context_from_history(cbd.ui_history, runtime=utils.extract_runtime(q))
        await utils.apply_menu_context(context=ctx, target=q, ui_registry=tg_ui_registry)
