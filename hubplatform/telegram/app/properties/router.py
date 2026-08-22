from __future__ import annotations

from pyconfigtree import Properties, BoolParameter
from aiogram.types import (
    Message,
    CallbackQuery as Query,
)
from aiogram.fsm.context import FSMContext
from pyconfigtree.exceptions import PyConfigTreeError

from hubplatform.i18n import Translator
from hubplatform.telegram import Router
from hubplatform.telegram.ui import UIManager
from hubplatform.telegram.app.ui_names import TelegramAppUINames

from . import states, builders, callbacks as cbs


properties_router = Router(name='hubplatform.pyconfigtree')


@properties_router.callback_query(cbs.NextValue.filter())
async def next_value(
    q: Query, cbd: cbs.NextValue, properties: Properties, ui_manager: UIManager
) -> None:
    param = properties.get_parameter(cbd.node_path)
    if not isinstance(param, BoolParameter):
        raise ValueError('Not a bool param.')
    await param.set_value(not param.value, save=True)
    await ui_manager.rerender_session(session_id=cbd.session_id, trigger=q)


@properties_router.callback_query(cbs.ManualValueInput.filter())
async def change_value_state(
    q: Query,
    properties: Properties,
    ui_manager: UIManager,
    cbd: cbs.ManualValueInput,
    state: FSMContext,
) -> None:
    node = properties.get_parameter(cbd.node_path)
    ctx = builders.ManualValueInputContext(
        node_path=cbd.node_path,
        open_next_session_id=cbd.session_id,
    )

    await ui_manager.open_menu(
        menu_id=TelegramAppUINames.properties.value_manual_input_menu,
        context=ctx,
        environment=q,
    )

    await states.ChangingParameterValueState(node=node, open_session=cbd.session_id).set(state)


@properties_router.message(states.ChangingParameterValueState.filter())
async def change_value(
    m: Message,
    state: FSMContext,
    translator: Translator,
    ui_manager: UIManager,
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

    await ui_manager.clone_session(session_id=data.open_session, environment=m)
    await ui_manager.close_session(session_id=data.open_session, trigger=m)
