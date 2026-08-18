from __future__ import annotations

from aiogram.types import CallbackQuery

from hubplatform.telegram.router import Router
from hubplatform.telegram.ui.registry import UIRegistry

from . import callbacks as cbs


router = Router(name='hubplatform.ui_router')


@router.callback_query(cbs.OpenMenu.filter())
async def open_menu(q: CallbackQuery, cbd: cbs.OpenMenu, ui_registry: UIRegistry) -> None:
    ctx_type = ui_registry.get_menu_context_type(cbd.context.menu_id)
    ctx = ctx_type.from_snapshot(cbd.context)
