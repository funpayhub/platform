from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Set
from typing import Any

from .category import ExpressionsCategory
from .definition import Expression, ExpressionDefinition
from .call_context import ExpressionContext


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionContext], dict[str, ExpressionDefinition]] = {}
        self._categories: dict[str, ExpressionsCategory] = {}


        self._expressions_tree: dict[Any, Any] = {}
        self._categories_tree: dict[Any, Any] = {}

        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def add_expression(
        self,
        expression: Expression | ExpressionDefinition,
        context_type: type[ExpressionContext],
        call_key: str,
        category: str | None = None,
    ) -> None:
        self._check_not_frozen()
        pass

    def add_category(self):
        self._check_not_frozen()

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

    def freeze(self) -> None:
        if self._frozen == True:
            return

    def _check_not_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(
                f'This operation available only when expressions manager is not frozen.'
            )

    def _check_frozen(self) -> None:
        if not self._frozen:
            raise RuntimeError(
                'This operation available only when expressions manager is frozen.'
            )
