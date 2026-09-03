from __future__ import annotations


__all__ = [
    'CreatingFileSourceState',
    'GoodsActionState',
]

from typing import Literal
from dataclasses import dataclass

from hubplatform.telegram.fsm import State


@dataclass
class CreatingFileSourceState(State, identifier='hubplatform.goods_sources.creating_file_source'):
    return_session_id: str
    input_session_id: str


@dataclass
class GoodsActionState(State, identifier='hubplatform.goods_sources.action'):
    source_id: str
    action: Literal['add', 'remove', 'replace']
    return_session_id: str
    input_session_id: str
