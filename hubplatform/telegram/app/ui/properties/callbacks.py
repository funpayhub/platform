from __future__ import annotations

from hubplatform.telegram.ui import MenuContextSnapshot
from hubplatform.telegram.callback_data import CallbackData


class NextValue(CallbackData, identifier='hubplatform.properties.next_value'):
    node_path: list[str]
    open_next: MenuContextSnapshot


class ManualValueInput(CallbackData, identifier='hubplatform.pyconfigtree.manual_value_input'):
    node_path: list[str]
    open_next: MenuContextSnapshot
