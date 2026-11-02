from __future__ import annotations

from typing import Iterable, Generator

from .category import CategoryPath
from .envelope import ExpressionEnvelope
from ..call_context import ExpressionContext


type _ExpressionsByCategory = dict[CategoryPath | None, dict[str, 'ExpressionEnvelope']]


class ExpressionsScope:
    def __init__(
        self,
        context_type: type[ExpressionContext],
        context_id: str | None = None,
    ) -> None:
        self._context_type = context_type
        self._id = context_id
        self._parent: ExpressionsScope | None = None
        self._subscopes: dict[type[ExpressionContext], ExpressionsScope] = {}
        self._expressions: dict[str, ExpressionEnvelope] = {}
        self._expressions_by_category: _ExpressionsByCategory = {}

    def _add_expressions(self, expressions: Iterable[ExpressionEnvelope], /) -> None:
        for expr in expressions:
            self._expressions[expr.call_key] = expr
            if expr.category not in self._expressions_by_category:
                self._expressions_by_category[expr.category] = {}
            self._expressions_by_category[expr.category][expr.call_key] = expr

    def _add_subscope(self, subscope: ExpressionsScope) -> None:
        if subscope.parent is not None:
            raise ValueError(
                f'Subscope {subscope.id!r} already has a parent {subscope.parent.id!r}.'
            )
        self._subscopes[subscope._context_type] = subscope
        subscope._parent = self

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def context_type(self) -> type[ExpressionContext]:
        return self._context_type

    @property
    def parent(self) -> ExpressionsScope | None:
        return self._parent

    @property
    def subscopes(self) -> dict[type[ExpressionContext], ExpressionsScope]:
        return self._subscopes.copy()

    @property
    def populated_subscopes(self) -> list[ExpressionsScope]:
        result: list[ExpressionsScope] = []
        for subscope in self._subscopes.values():
            if subscope._id is None:
                result.extend(subscope.populated_subscopes)
            elif subscope._has_expressions_in_subtree():
                result.append(subscope)
        return result

    def _has_expressions_in_subtree(self) -> bool:
        return bool(self._expressions) or any(
            i._has_expressions_in_subtree() for i in self._subscopes.values()
        )

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def chain_to_root(self) -> Generator[ExpressionsScope, None, None]:
        curr: ExpressionsScope | None = self
        while curr is not None:
            yield curr
            curr = curr._parent

    @property
    def scope_expressions(self) -> dict[str, ExpressionEnvelope]:
        return self._expressions.copy()

    @property
    def scope_expressions_by_category(self) -> _ExpressionsByCategory:
        return {k: v.copy() for k, v in self._expressions_by_category.items()}

    @property
    def available_expressions(self) -> dict[str, ExpressionEnvelope]:
        expressions = [i._expressions for i in self.chain_to_root]
        result = {}
        for j in reversed(expressions):
            result.update(j)
        return result

    @property
    def available_expressions_by_category(self) -> _ExpressionsByCategory:
        expressions = self.available_expressions
        result: _ExpressionsByCategory = {}
        for call_key, expr in expressions.items():
            if expr.category not in result:
                result[expr.category] = {}
            result[expr.category][call_key] = expr
        return result
