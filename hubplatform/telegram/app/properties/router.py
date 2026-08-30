from __future__ import annotations

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
from hubplatform.telegram.app.menu_ids import MenuIDs

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
    await q.answer()


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
        menu_id=MenuIDs.properties.value_manual_input_menu,
        context=ctx,
        environment=q,
    )

    await states.ChangingParameterValueState(
        node=node,  # type: ignore[arg-type]
        open_session=cbd.session_id,
    ).set(state)
    await q.answer()


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
) -> None:
    node = properties.get_parameter(cbd.node_path)
    if not isinstance(node, ListParameter):
        raise ValueError(f'{node.path} is not a ListParameter.')

    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        trigger=q,
        expected_revision=cbd.revision,
        rerender=True,
    ) as s:
        await node.pop_items(*cbd.selected)
        s.current.context_fields['selected_indexes'] = []


@props_router.callback_query(cbs.ListAction.filter(rule=F.action.in_(['move_up', 'move_down'])))
async def move_selected_items(
    q: Query,
    properties: Properties,
    ui_manager: UIManager,
    cbd: cbs.ListAction,
) -> None:
    node = properties.get_parameter(cbd.node_path)
    if not isinstance(node, ListParameter):
        raise ValueError(f'{node.path} is not a ListParameter.')
    selected = sorted(cbd.selected)

    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        trigger=q,
        expected_revision=cbd.revision,
        rerender=True,
    ) as s:
        value = node.value
        if cbd.action == 'move_up' and selected[0] <= 0:
            await q.answer()
            return
        if cbd.action == 'move_down' and selected[-1] >= len(node.value):
            await q.answer()
            return

        for index in selected if cbd.action == 'move_up' else reversed(selected):
            to = index - 1 if cbd.action == 'move_up' else index + 1
            value[index], value[to] = value[to], value[index]
        await node.set_value(value)
        new_selected = [i + (-1 if cbd.action == 'move_up' else +1) for i in selected]
        s.current.context_fields['selected_indexes'] = new_selected  # type: ignore[assignment]


@props_router.callback_query(cbs.InsertItemsInList.filter())
async def inserting_value_state(
    q: Query,
    properties: Properties,
    ui_manager: UIManager,
    cbd: cbs.InsertItemsInList,
    state: FSMContext,
) -> None:
    node = properties.get_parameter(cbd.node_path)
    ctx = builders.ManualValueInputContext(
        node_path=cbd.node_path,
        open_next_session_id=cbd.session_id,
    )

    await ui_manager.open_menu(
        menu_id=MenuIDs.properties.list_new_items_input_menu,
        context=ctx,
        environment=q,
    )

    await states.InsertingListItems(
        node=node,  # type: ignore[arg-type]
        index=cbd.index,
        before=cbd.before,
        open_session=cbd.session_id,
    ).set(state)
    await q.answer()


@props_router.message(states.InsertingListItems.filter())
async def insert_list_items(
    m: Message, state: FSMContext, translator: Translator, ui_manager: UIManager
) -> None:
    if not m.text:
        return
    data = await states.InsertingListItems.get(state)
    values = [i.replace('\\n', '\n') if i != '-' else '' for i in m.text.splitlines()]
    try:
        if data.index is None:
            await data.node.add_items(*values)
        else:
            new_value = data.node.value
            index = data.index if data.before else data.index + 1
            new_value[index:index] = values
            await data.node.set_value(new_value)
        await state.clear()
    except PyConfigTreeError:
        await m.answer(translator.translate('error-changing-parameter-value'))
        return

    if data.before and data.index is not None:
        async with ui_manager.edit_session(session_id=data.open_session) as s:
            s.current.context_fields['selected_indexes'] = [data.index + len(values)]

    await ui_manager.clone_session(session_id=data.open_session, environment=m)
    await ui_manager.close_session(session_id=data.open_session, trigger=m)
