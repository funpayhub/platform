from __future__ import annotations

from utils import apply_menu_snapshot
from pyconfigtree import Properties, BoolParameter
from aiogram.types import CallbackQuery as Query
from aiogram.fsm.context import FSMContext

from hubplatform.telegram import Router
from hubplatform.telegram.ui import UIRegistry

from . import callbacks as cbs


properties_router = Router(name='hubplatform.pyconfigtree')


@properties_router.callback_query(cbs.NextValue.filter())
async def next_value(
    q: Query, cbd: cbs.NextValue, properties: Properties, tg_ui_registry: UIRegistry
) -> None:
    param = properties.get_parameter(cbd.node_path)
    if not isinstance(param, BoolParameter):
        raise ValueError('Not a bool param.')
    await param.set_value(not param.value, save=True)
    await apply_menu_snapshot(cbd.open_next, q, ui_registry=tg_ui_registry)


@properties_router.callback_query(cbs.ManualValueInput.filter())
async def change_value_state(
    q: Query,
    properteis: Properties,
    tg_ui_registry: UIRegistry,
    cbd: cbs.ManualValueInput,
    state: FSMContext,
) -> None: ...
