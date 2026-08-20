from __future__ import annotations

from contextlib import suppress

from pyconfigtree import Properties, BoolParameter
from aiogram.types import (
    Message,
    CallbackQuery as Query,
)
from aiogram.fsm.context import FSMContext
from pyconfigtree.exceptions import PyConfigTreeError

from hubplatform.i18n import Translator
from hubplatform.telegram import Router
from hubplatform.telegram.ui import UIRegistry
from hubplatform.telegram.app.ui import utils
from hubplatform.telegram.app.ui_names import TelegramAppUINames as ui_names

from . import states, builders, callbacks as cbs


properties_router = Router(name='hubplatform.pyconfigtree')


@properties_router.callback_query(cbs.NextValue.filter())
async def next_value(
    q: Query, cbd: cbs.NextValue, properties: Properties, tg_ui_registry: UIRegistry
) -> None:
    param = properties.get_parameter(cbd.node_path)
    if not isinstance(param, BoolParameter):
        raise ValueError('Not a bool param.')
    await param.set_value(not param.value, save=True)
    await utils.apply_menu_snapshot(cbd.open_next, q, ui_registry=tg_ui_registry)


@properties_router.callback_query(cbs.ManualValueInput.filter())
async def change_value_state(
    q: Query,
    properties: Properties,
    tg_ui_registry: UIRegistry,
    cbd: cbs.ManualValueInput,
    state: FSMContext,
) -> None:
    node = properties.get_parameter(cbd.node_path)
    ctx = builders.ManualValueInputContext(
        menu_id=ui_names.properties.value_manual_input_menu,
        node_path=cbd.node_path,
        open_next=cbd.open_next,
        runtime=utils.extract_runtime(q),
    )
    msg = await utils.apply_menu_context(ctx, q, new_message=True, ui_registry=tg_ui_registry)
    await states.ChangingParameterValueState(
        node=node, open_next=cbd.open_next, state_message_id=msg.message_id
    ).set(state)


@properties_router.message(states.ChangingParameterValueState.filter())
async def change_value(
    m: Message,
    state: FSMContext,
    translator: Translator,
    tg_ui_registry: UIRegistry,
) -> None:
    data = await states.ChangingParameterValueState.get(state)
    value = m.text if m.text != '-' else ''
    try:
        await data.node.set_value(value)
        await state.clear()
    except PyConfigTreeError:
        await m.answer(
            translator.translate('error-changing-parameter-value'),
        )
        return

    await utils.apply_menu_snapshot(
        data.open_next, m, ui_registry=tg_ui_registry, new_message=True
    )
    with suppress(Exception):
        await m.bot.delete_message(chat_id=m.chat.id, message_id=data.state_message_id)


# list operations
