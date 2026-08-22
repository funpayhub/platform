from __future__ import annotations


__all__ = [
    'MenuFrame',
    'MenuSession',
]

from typing import TYPE_CHECKING

from pydantic import Field, BaseModel, JsonValue


if TYPE_CHECKING:
    from hubplatform.telegram.ui import MenuContext, MenuViewState


class MenuFrame(BaseModel):
    menu_id: str
    keyboard_page: int = 0
    text_page: int = 0
    context_fields: dict[str, JsonValue] = Field(default_factory=dict)

    @classmethod
    def from_menu_context(
        cls,
        menu_id: str,
        menu_context: MenuContext,
        view: MenuViewState | None = None,
        *,
        keyboard_page: int | None = None,
        text_page: int | None = None,
    ) -> MenuFrame:
        text = text_page if text_page is not None else view.text_page if view is not None else 0
        kb = (
            keyboard_page
            if keyboard_page is not None
            else view.keyboard_page
            if view is not None
            else 0
        )

        return MenuFrame(
            menu_id=menu_id, keyboard_page=text, text_page=kb, context_fields=menu_context.dump()
        )


class MenuSession(BaseModel):
    id: str
    chat_id: int | None = None
    thread_id: int | None = None
    message_id: int | None = None
    current: MenuFrame
    history: list[MenuFrame] = Field(default_factory=list)
    revision: int = 0
