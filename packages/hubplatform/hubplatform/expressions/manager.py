from hubplatform.expressions.call_context import ExpressionCallContext
from hubplatform.expressions.definition import ExpressionDefinition


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionCallContext], dict[str, ExpressionDefinition]] = {}

    def get_available_expressions(
        self,
        context_type: type[ExpressionCallContext]
    ) -> dict[type[ExpressionCallContext], dict[str, ExpressionDefinition]]:
        context_types = context_type.get_available_context_types()
        result = {}
        for i in context_types:
            if i not in self._expressions:
                continue
            result[i] = self._expressions.copy()
        return result
