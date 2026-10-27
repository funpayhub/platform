from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Set

from .category import ExpressionsCategory
from .definition import Expression, ExpressionDefinition
from .call_context import ExpressionContext


@dataclass(frozen=True)
class ExpressionEnvelope:
    expression: ExpressionDefinition
    categories: Set[str]


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionContext], dict[str, ExpressionDefinition]] = {}
        self._categories: dict[str, ExpressionsCategory] = {}

    def add_expression(
        self,
        expression: Expression | ExpressionDefinition,
        context_type: type[ExpressionContext],
        call_key: str,
        category: str | None = None,
    ) -> None: ...

    def add_category(self):
        pass

    def get_available_expressions(
        self, context_type: type[ExpressionContext]
    ) -> dict[type[ExpressionContext], dict[str, ExpressionDefinition]]:
        context_types = context_type.get_available_context_types()
        result = {}
        for i in context_types:
            if i not in self._expressions:
                continue
            result[i] = self._expressions.copy()
        return result
