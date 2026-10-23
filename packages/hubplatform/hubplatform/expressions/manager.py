from __future__ import annotations

from hubplatform.expressions.definition import ExpressionDefinition
from hubplatform.expressions.call_context import ExpressionContext


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionContext], dict[str, ExpressionDefinition]] = {}

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
