from __future__ import annotations


__all__ = ['ChangingParameterValueState']

from typing import Any
from dataclasses import dataclass

from pyconfigtree import MutableParameter

from hubplatform.telegram.ui import MenuContextSnapshot
from hubplatform.telegram.fsm import State


@dataclass
class ChangingParameterValueState(
    State, identifier='hubplatform.pyconfigtree.changing_parameter_value'
):
    node: MutableParameter[Any]
    open_next: MenuContextSnapshot
    state_message_id: int
