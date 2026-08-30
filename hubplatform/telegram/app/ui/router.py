from __future__ import annotations

from contextlib import suppress

from aiogram.types import Message, CallbackQuery as Query
from aiogram.fsm.context import FSMContext

from hubplatform.telegram.ui import UIManager, MenuContext, MenuViewState
from hubplatform.telegram.router import Router
from hubplatform.telegram.app.menu_ids import MenuIDs

from . import states, callbacks as cbs


ui_router = Router(name='hubplatform.ui_router')


@ui_router.callback_query(cbs.OpenMenu.filter())
async def open_menu(q: Query, cbd: cbs.OpenMenu, ui_manager: UIManager) -> None:
    ctx_type = ui_manager.ui_registry.get_menu_context_type(cbd.menu_id)
    ctx = ctx_type.model_validate(cbd.context)

    await ui_manager.replace_menu(
        session_id=cbd.session_id,
        menu_id=cbd.menu_id,
        context=ctx,
        trigger=q,
        push_current_to_history=cbd.move_to_history,
        expected_revision=cbd.revision,
        view_state=MenuViewState(keyboard_page=cbd.keyboard_page, text_page=cbd.text_page),
    )


@ui_router.callback_query(cbs.ChangePageTo.filter())
async def change_page(q: Query, cbd: cbs.ChangePageTo, ui_manager: UIManager) -> None:
    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        trigger=q,
        expected_revision=cbd.revision,
        rerender=True,
    ) as session:
        if cbd.keyboard_page is not None:
            session.current.keyboard_page = cbd.keyboard_page
        if cbd.text_page is not None:
            session.current.text_page.update(cbd.text_page)

    await q.answer()


@ui_router.callback_query(cbs.ClearState.filter())
async def clear(q: Query, cbd: cbs.ClearState, ui_manager: UIManager, state: FSMContext) -> None:
    await state.clear()
    if isinstance(q.message, Message):
        await q.message.delete()

    if cbd.open_session_id is not None:
        await ui_manager.clone_session(session_id=cbd.open_session_id, environment=q)


@ui_router.callback_query(cbs.GoBack.filter())
async def go_back(q: Query, ui_manager: UIManager, cbd: cbs.GoBack) -> None:
    async with ui_manager.edit_session(session_id=cbd.session_id, rerender=True, trigger=q) as s:
        s.current = s.history.pop()


@ui_router.callback_query(cbs.ToggleConfirmation.filter())
async def toggle_confirmation(
    q: Query, ui_manager: UIManager, cbd: cbs.ToggleConfirmation
) -> None:
    key = f'open_confirmation:{cbd.confirmation_id}'
    async with ui_manager.edit_session(
        session_id=cbd.session_id,
        rerender=True,
        trigger=q,
        expected_revision=cbd.revision,
    ) as s:
        data = s.current.context_fields.get('data')
        if not isinstance(data, dict):
            data = {}
            s.current.context_fields['data'] = data

        if not data.pop(key, None):
            data[key] = True

    await q.answer()


@ui_router.callback_query(cbs.Dummy.filter())
async def dummy(q: Query) -> None:
    await q.answer()


@ui_router.callback_query(cbs.ChangePageManually.filter())
async def enter_changing_page_state(
    q: Query, cbd: cbs.ChangePageTo, ui_manager: UIManager, state: FSMContext
) -> None:
    result = await ui_manager.open_menu(
        menu_id=MenuIDs.basic_ui.manual_change_page_menu,
        context=MenuContext(),
        environment=q,
    )

    await states.ChangingMenuPage(
        changing_in_session_id=cbd.session_id, state_session=result.session.id
    ).set(state)
    await q.answer()


@ui_router.message(states.ChangingMenuPage.filter())
async def change_page_from_state(m: Message, ui_manager: UIManager, state: FSMContext) -> None:
    data = await states.ChangingMenuPage.get(state)
    if not m.text or not m.text.isnumeric():
        return
    page = int(m.text) - 1
    if page < 0:
        return

    with suppress(Exception):
        async with ui_manager.edit_session(
            data.changing_in_session_id, rerender=True, trigger=m
        ) as session:
            session.current.keyboard_page = page

    with suppress(Exception):
        await ui_manager.close_session(data.state_session, trigger=m)

    await state.clear()
