from __future__ import annotations

from typing import Any, TypeAlias
from dataclasses import dataclass

from .category import ExpressionsCategory
from .definition import Expression, ExpressionDefinition
from .call_context import ExpressionContext


_ContextTree: TypeAlias = dict[type[ExpressionContext], '_ContextTree']
_CategoriesTree: TypeAlias = dict[str, '_CategoriesTree']


@dataclass(frozen=True)
class ExpressionEnvelope:
    expression: ExpressionDefinition
    category: str | None = None


class ExpressionsManager:
    def __init__(self) -> None:
        self._expressions: dict[type[ExpressionContext], dict[str, ExpressionEnvelope]] = {}
        self._categories: dict[str, ExpressionsCategory] = {}

        self._context_type_to_id: dict[type[ExpressionContext], str] = {}
        self._id_to_context_type: dict[str, type[ExpressionContext]] = {}

        self._context_tree: dict[Any, Any] = {}
        self._categories_tree: dict[Any, Any] = {}

        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def add_context(self, context_type: type[ExpressionContext], id: str) -> None:
        self._check_not_frozen()
        if context_type in self._context_type_to_id:
            raise ValueError(
                f"Context type '{context_type.__module__}.{context_type.__qualname__}' "
                f'already registered under ID {self._context_type_to_id[context_type]!r}.'
            )

        if id in self._id_to_context_type:
            ctx_type = self._id_to_context_type[id]
            raise ValueError(
                f'ID {id!r} is already acquired by '
                f"'{ctx_type.__module__}.{ctx_type.__qualname__}'."
            )

        self._context_type_to_id[context_type] = id
        self._id_to_context_type[id] = context_type

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
        if self._frozen:
            return

        self._check_all_context_types_are_registered()
        self._context_tree = self._build_context_tree()
        self._categories_tree = self._build_categories_tree()
        self._frozen = True

    def _check_not_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(
                'This operation available only when expressions manager is not frozen.'
            )

    def _check_frozen(self) -> None:
        if not self._frozen:
            raise RuntimeError('This operation available only when expressions manager is frozen.')

    def _build_context_tree(self) -> _ContextTree:
        result = {}
        for context_type in self._expressions:
            curr = result
            for curr_context_type in context_type.get_available_context_types():
                if curr_context_type not in curr:
                    if curr_context_type not in self._expressions:
                        continue
                    curr[curr_context_type] = {}
                curr = curr[curr_context_type]
        return result

    def _build_categories_tree(self) -> dict[Any, Any]:
        result = {}
        for full_category in self._categories:
            split = full_category.split('.')
            curr = result
            curr_name = ''

            for cat in split:
                curr_name += ('.' if curr_name else '') + cat
                if cat not in curr:
                    curr[cat] = {}
                curr = curr[cat]
                continue
        return result

    def _check_all_context_types_are_registered(self) -> None:
        for context_type in self._expressions:
            if context_type not in self._context_type_to_id:
                raise RuntimeError(
                    f'Context type {context_type.__module__}.{context_type.__qualname__} '
                    f'has bound expressions, but it is not registered.'
                )
