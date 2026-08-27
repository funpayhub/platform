from __future__ import annotations


__all__ = [
    'OpenMenu',
    'ChangePageTo',
    'GoBack',
    'ClearState',
    'ChangePageManually',
    'Dummy',
]

from pydantic import JsonValue

from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.ui.session_callback_data import SessionCallbackData


class OpenMenu(SessionCallbackData, identifier='hubplatform.open_menu'):
    menu_id: str
    keyboard_page: int = 0
    text_page: int = 0
    context: dict[str, JsonValue]
    new_message: bool = False
    move_to_history: bool = True


class ChangePageTo(SessionCallbackData, identifier='hubplatform.change_page_to'):
    keyboard_page: int | None = None
    text_page: int | None = None


class ChangePageManually(SessionCallbackData, identifier='hubplatform.change_page_manually'):
    max_pages: int | None = None


class GoBack(SessionCallbackData, identifier='hubplatform.go_back'):
    pass


class ClearState(CallbackData, identifier='hubplatform.clear_state'):
    open_session_id: str | None = None


class Dummy(CallbackData, identifier='hubplatform.dummy'):
    pass
