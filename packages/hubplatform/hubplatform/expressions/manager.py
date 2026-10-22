from typing import Any

from hubplatform.expressions.call_context import ExpressionCallContext
from hubplatform.expressions.definition import ExpressionDefinition


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionCallContext], dict[str, ExpressionDefinition]] = {}

    def get_available_expressions(self, context_type: type[ExpressionCallContext]) -> dict[str, Any]:
        for