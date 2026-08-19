from __future__ import annotations


__all__ = [
    'OpenMenu',
    'ChangePageTo',
    'Dummy',
]

from typing import Literal

from hubplatform.telegram.ui import MenuContext, UICallbackData, MenuContextSnapshot


class OpenMenu(UICallbackData, identifier='hubplatform.open_menu'):
    snapshot: MenuContextSnapshot
    new_message: bool = False

    @classmethod
    def from_context(cls, menu_context: MenuContext, new_message: bool = False) -> OpenMenu:
        return OpenMenu(
            snapshot=menu_context.snapshot(),
            new_message=new_message,
        )


class ChangePageTo(UICallbackData, identifier='hubplatform.change_page_to'):
    keyboard_page: int | None = None
    text_page: int | None = None


class ClearState(UICallbackData, identifier='hubplatform.clear_state'):
    mode: Literal['delete', 'go_back'] = 'delete'


class Dummy(UICallbackData, identifier='hubplatform.dummy'):
    pass
