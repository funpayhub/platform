from __future__ import annotations

from typing import Any

from aiogram import F
from pyconfigtree import Properties, BoolParameter, ListParameter
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


props_router = Router(name='hubplatform.pyconfigtree')


@props_router.callback_query(cbs.NextValue.filter())
async def next_value(
    q: Query, cbd: cbs.NextValue, properties: Properties, ui_manager: UIManager
) -> None:
    param = properties.get_parameter(cbd.node_path)
    if not isinstance(param, BoolParameter):
        raise ValueError('Not a bool param.')
    await param.set_value(not param.value, save=True)
    await ui_manager.rerender_session(session_id=cbd.session_id, trigger=q)


@props_router.callback_query(cbs.ManualValueInput.filter())
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


@props_router.message(states.ChangingParameterValueState.filter())
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


@props_router.callback_query(cbs.ListAction.filter(rule=F.action == 'remove'))
async def remove_selected_items(
    q: Query,
    properties: Properties,
    ui_manager: UIManager,
    cbd: cbs.ListAction,
):
    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        trigger=q,
        expected_revision=cbd.revision,
        rerender=True,
    ) as s:
        selected_indexes: list[int] = s.current.context_fields['selected_indexes']  # type: ignore
        selected_indexes = sorted(selected_indexes)
        path: list[str] = s.current.context_fields['node_path']  # type: ignore
        node: ListParameter[Any] = properties.get_parameter(path)  # type: ignore

        removed = 0
        for index in selected_indexes:
            try:
                node._value.pop(index - removed)
                removed += 1
            except IndexError:
                continue

        await node.save()
        s.current.context_fields['selected_indexes'] = []


@props_router.callback_query(cbs.ListAction.filter(rule=F.action.in_(['move_up', 'move_down'])))
async def move_selected_items(
    q: Query,
    properties: Properties,
    ui_manager: UIManager,
    cbd: cbs.ListAction,
):
    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        trigger=q,
        expected_revision=cbd.revision,
        rerender=True,
    ) as s:
        selected_indexes: list[int] = s.current.context_fields['selected_indexes']  # type: ignore
        selected_indexes = sorted(selected_indexes)
        path: list[str] = s.current.context_fields['node_path']  # type: ignore
        node: ListParameter[Any] = properties.get_parameter(path)  # type: ignore

        if cbd.action == 'move_up' and selected_indexes[0] <= 0:
            await q.answer()
            return
        if cbd.action == 'move_down' and selected_indexes[-1] >= len(node.value):
            await q.answer()
            return

        for index in selected_indexes if cbd.action == 'move_up' else reversed(selected_indexes):
            to = index - 1 if cbd.action == 'move_up' else index + 1
            node._value[index], node._value[to] = node._value[to], node._value[index]

        await node.save()
        new_selected = [i + (-1 if cbd.action == 'move_up' else +1) for i in selected_indexes]
        s.current.context_fields['selected_indexes'] = new_selected
