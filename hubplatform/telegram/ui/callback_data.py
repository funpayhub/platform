from __future__ import annotations


__all__ = ['UICallbackData']

from pydantic import Field

from hubplatform.telegram.callback_data import CallbackData

from .types import MenuContextSnapshot


class UICallbackData(CallbackData, identifier='hubplatform_ui_callback_data'):
    ui_history: list[MenuContextSnapshot] = Field(default_factory=list)
    keyboard_page: int = 0
    text_page: int = 0
