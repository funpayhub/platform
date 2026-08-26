from __future__ import annotations

from typing import Any, Sequence
from dataclasses import dataclass


@dataclass
class Call:
    name: str
    args: Sequence[Any]
    kwargs: dict[str, Any]

    def __post_init__(self) -> None:
        from .parsing import _check_token

        _check_token(self.name, 'Call name')

    def encode(self) -> str:
        from .parsing import call_encoder

        return call_encoder.encode(self.name, self.args, self.kwargs)


@dataclass(frozen=True)
class StringWithCalls:
    string: str
    decoded: list[str | Call]
    call_spans: dict[tuple[int, int], Call]
