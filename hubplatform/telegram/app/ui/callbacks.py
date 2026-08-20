from __future__ import annotations


__all__ = [
    'UICallbackData',
    'PageableUICallbackData',
    'OpenMenu',
    'ChangePageTo',
    'Dummy',
]


from pydantic import Field

from hubplatform.telegram.ui import MenuContext, MenuContextSnapshot
from hubplatform.telegram.callback_data import CallbackData


class UICallbackData(CallbackData, identifier='hubplatform_ui_callback_data'):
    ui_history: list[MenuContextSnapshot] = Field(default_factory=list)


class PageableUICallbackData(UICallbackData, identifier='hubplatform.pageable_callback_data'):
    keyboard_page: int = 0
    text_page: int = 0


class OpenMenu(CallbackData, identifier='hubplatform.open_menu'):
    snapshot: MenuContextSnapshot
    new_message: bool = False

    @classmethod
    def from_context(cls, menu_context: MenuContext, new_message: bool = False) -> OpenMenu:
        return OpenMenu(
            snapshot=menu_context.snapshot(),
            new_message=new_message,
        )


class ChangePageTo(CallbackData, identifier='hubplatform.change_page_to'):
    snapshot: MenuContextSnapshot
    keyboard_page: int | None = None
    text_page: int | None = None


class ClearState(CallbackData, identifier='hubplatform.clear_state'):
    open_next: MenuContextSnapshot | None = None


class Dummy(CallbackData, identifier='hubplatform.dummy'):
    pass
