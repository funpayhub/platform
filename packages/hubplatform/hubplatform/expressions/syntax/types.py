from __future__ import annotations

from typing import Any, Sequence
from dataclasses import dataclass
from collections.abc import Mapping

lazy from .parsing import call_encoder, _TOKEN_ALLOWED_CHARS


@dataclass
class Call:
    name: str
    args: Sequence[Any]
    kwargs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f'Call name must be a string, not {type(self.name)}.')
        if not self.name:
            raise ValueError(f'Call name cannot be empty.')

        for index, char in enumerate(self.name):
            if char not in _TOKEN_ALLOWED_CHARS:
                raise ValueError(
                    f'Call name {self.name!r} contains not allowed char {char!r} at position '
                    f"{index}. Call name can only contain ASCII letters, digits and '_'.",
                )

    def encode(self) -> str:
        return call_encoder.encode(self)


@dataclass(frozen=True)
class StringWithCalls:
    string: str
    decoded: Sequence[str | Call]
    call_spans: Mapping[tuple[int, int], Call]
