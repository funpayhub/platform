from __future__ import annotations


__all__ = ['ExpressionsScope']

from types import MappingProxyType
from collections.abc import Mapping, Sequence

from ..traits import Trait
from .category import CategoryPath
from .envelope import ExpressionEnvelope


type _ExpressionsByCategory = dict[CategoryPath | None, dict[str, ExpressionEnvelope]]


class ExpressionsScope:
    """Expressions available for one container shape (a set of trait types), with overrides
    already resolved. Created and cached by ``ExpressionsManager.get_scope()``."""

    def __init__(
        self,
        shape: frozenset[type[Trait]],
        expressions: Mapping[str, ExpressionEnvelope],
        ambiguous: Mapping[str, Sequence[ExpressionEnvelope]],
    ) -> None:
        self._shape = shape
        self._expressions = MappingProxyType(dict(expressions))
        self._ambiguous = MappingProxyType({k: tuple(v) for k, v in ambiguous.items()})

    @property
    def shape(self) -> frozenset[type[Trait]]:
        return self._shape

    @property
    def expressions(self) -> Mapping[str, ExpressionEnvelope]:
        """Every expression available for the shape, by call key."""
        return self._expressions

    @property
    def ambiguous(self) -> Mapping[str, tuple[ExpressionEnvelope, ...]]:
        """Call keys with several equally specific expressions. Calling them is an error."""
        return self._ambiguous

    @property
    def expressions_by_category(self) -> _ExpressionsByCategory:
        result: _ExpressionsByCategory = {}
        for call_key, envelope in self._expressions.items():
            result.setdefault(envelope.category, {})[call_key] = envelope
        return result

    def __repr__(self) -> str:
        names = ', '.join(sorted(i.__qualname__ for i in self._shape))
        return f'<ExpressionsScope ({names})>'
