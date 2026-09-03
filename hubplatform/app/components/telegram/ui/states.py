from __future__ import annotations

from dataclasses import dataclass

from hubplatform.telegram.fsm import State


@dataclass
class ChangingMenuPage(State, identifier='hubplatform.basic_ui.changing_menu_page'):
    changing_in_session_id: str
    state_session: str
