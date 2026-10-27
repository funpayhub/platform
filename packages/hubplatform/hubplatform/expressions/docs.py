from __future__ import annotations


__all__ = [
    'ExpressionDocs',
    'ArgDocs',
]

from types import MappingProxyType
from typing import Literal
from collections.abc import Mapping


class _DocsString(str):
    def with_call_key(self, call_key: str) -> str:
        return self.replace('{call_key}', call_key)


class ExpressionDocs:
    def __init__(
        self,
        *,
        overview: str,
        args_doc: Mapping[str, ArgDocs] | None = None,
    ) -> None:
        self._overview = _DocsString(overview)
        self._arg_docs = dict(args_doc) if args_doc is not None else {}
        self._arg_docs_proxy = MappingProxyType(self._arg_docs)

    @property
    def overview(self) -> _DocsString:
        return self._overview

    @property
    def arg_docs(self) -> Mapping[str, ArgDocs]:
        return self._arg_docs_proxy


class ArgDocs:
    def __init__(
        self,
        *,
        name: str,
        key: str,
        overview: str,
        default: str | None = None,
        possible_values: str | Mapping[str, str],
        kind: Literal['normal', 'positional_only', 'keyword_only'] = 'normal'
    ) -> None:
        self._name = name
        self._key = key
        self._overview = _DocsString(overview)
        self._default = _DocsString(default)
        if isinstance(possible_values, str):
            self._possible_values = _DocsString(possible_values)
        else:
            self._possible_values = {
                _DocsString(k): _DocsString(v) for k, v in possible_values.items()
            }
        self._kind = kind

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        return self._key

    @property
    def overview(self) -> _DocsString:
        return self._overview

    @property
    def default(self) -> _DocsString:
        return self._default

    @property
    def possible_values(self) -> _DocsString | Mapping[_DocsString, _DocsString]:
        return self._possible_values \
            if isinstance(self._possible_values, str) \
            else MappingProxyType(self._possible_values)

    @property
    def kind(self) -> Literal['normal', 'positional_only', 'keyword_only']:
        return self._kind
