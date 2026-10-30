from __future__ import annotations

from typing import Any, Sequence
from dataclasses import dataclass
from collections.abc import Mapping

lazy from .parsing import _check_token, call_encoder


@dataclass
class Call:
    name: str
    args: Sequence[Any]
    kwargs: Mapping[str, Any]

    def __post_init__(self) -> None:
        _check_token(self.name, 'Call name', allow_leading_digit=True)

    def encode(self) -> str:
        return call_encoder.encode(self)

    def __hash__(self) -> int:
        return id(self)


@dataclass(frozen=True)
class StringWithCalls:
    string: str
    decoded: Sequence[str | Call]
    call_spans: Mapping[tuple[int, int], Call]
