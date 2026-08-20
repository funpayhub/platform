from __future__ import annotations

from typing import Literal

from hubplatform.telegram.ui import MenuContextSnapshot
from hubplatform.telegram.callback_data import CallbackData


class NextValue(CallbackData, identifier='hubplatform.properties.next_value'):
    node_path: list[str]
    open_next: MenuContextSnapshot


class ManualValueInput(CallbackData, identifier='hubplatform.properties.manual_value_input'):
    node_path: list[str]
    open_next: MenuContextSnapshot


class ListAction(CallbackData, identifier='hubplatform.properties.list_action'):
    node_path: list[str]
    action: Literal['move_up', 'move_down', 'remove']
    selected: set[int]
