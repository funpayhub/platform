from __future__ import annotations


__all__ = [
    'ExpressionDocs',
    'ArgDocs',
]

from typing import Literal
from types import MappingProxyType
from collections.abc import Mapping, Sequence


class _DocsString(str):
    def with_call_key(self, call_key: str) -> str:
        return self.replace('{call_key}', call_key)


class ExpressionDocs:
    def __init__(
        self,
        *,
        name: str,
        overview: str,
        args_doc: Mapping[str, ArgDocs] | None = None,
        example_usages: Sequence[ExampleUsage] | None = None,
    ) -> None:
        self._name = _DocsString(name)
        self._overview = _DocsString(overview)
        self._arg_docs = dict(args_doc) if args_doc is not None else {}
        self._arg_docs_proxy = MappingProxyType(self._arg_docs)
        self._example_usages = tuple(example_usages) if example_usages is not None else ()

    @property
    def name(self) -> _DocsString:
        return self._name

    @property
    def overview(self) -> _DocsString:
        return self._overview

    @property
    def arg_docs(self) -> Mapping[str, ArgDocs]:
        return self._arg_docs_proxy

    @property
    def example_usages(self) -> tuple[ExampleUsage, ...]:
        return self._example_usages


class ExampleUsage:
    def __init__(
        self,
        *,
        example: str,
        description: str,
    ) -> None:
        self._example = _DocsString(example)
        self._description = _DocsString(description)

    @property
    def example(self) -> _DocsString:
        return self._example

    @property
    def description(self) -> _DocsString:
        return self._description


class ArgDocs:
    def __init__(
        self,
        *,
        name: str,
        key: str,
        overview: str,
        default: str | None = None,
        possible_values: str | Mapping[str, str],
        kind: Literal['normal', 'positional_only', 'keyword_only'] = 'normal',
    ) -> None:
        self._name = name
        self._key = key
        self._overview = _DocsString(overview)
        self._default = _DocsString(default)

        self._possible_values: _DocsString | Mapping[_DocsString, _DocsString]
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
        return (
            self._possible_values
            if isinstance(self._possible_values, str)
            else MappingProxyType(self._possible_values)
        )

    @property
    def kind(self) -> Literal['normal', 'positional_only', 'keyword_only']:
        return self._kind
