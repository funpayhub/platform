from __future__ import annotations


__all__ = ['ChangingParameterValueState']

from typing import Any
from dataclasses import dataclass

from pyconfigtree import ListParameter, MutableParameter

from hubplatform.telegram.fsm import State


@dataclass
class ChangingParameterValueState(
    State, identifier='hubplatform.properties.changing_parameter_value'
):
    node: MutableParameter[Any]
    open_session: str
    delete_message: int | None = None


@dataclass
class InsertingListItems(State, identifier='hubplatform.properties.adding_list_items'):
    node: ListParameter[Any]
    open_session: str
    index: int | None = None
    before: bool = False
    delete_message: int | None = None
