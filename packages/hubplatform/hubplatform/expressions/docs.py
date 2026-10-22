from __future__ import annotations


__all__ = [
    'ExpressionDocs',
    'ArgDocs',
]

from typing import Literal
from dataclasses import field, dataclass
from collections.abc import Mapping


@dataclass
class ExpressionDocs:
    overview: str
    args_doc: Mapping[str, ArgDocs] = field(default_factory=dict)


@dataclass(kw_only=True)
class ArgDocs:
    name: str
    key: str
    overview: str
    default: str | None = None
    possible_values: str | dict[str, str]
    kind: Literal['normal', 'positional_only', 'keyword_only'] = 'normal'
