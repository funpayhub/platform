from __future__ import annotations

from typing import Literal

from pydantic import Field

from hubplatform.telegram.ui.session_callback_data import (
    SessionCallbackData,
    session_id_from_context,
)


class NextValue(SessionCallbackData, identifier='hubplatform.properties.next_value'):
    node_path: list[str]


class ManualValueInput(
    SessionCallbackData, identifier='hubplatform.properties.manual_value_input'
):
    node_path: list[str]
    open_next_session_id: str = Field(default_factory=session_id_from_context)


class ListAction(SessionCallbackData, identifier='hubplatform.properties.list_action'):
    node_path: list[str]
    selected: set[int] = Field(default_factory=set)
    action: Literal['move_up', 'move_down', 'remove']
