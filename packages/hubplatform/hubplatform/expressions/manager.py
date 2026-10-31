from __future__ import annotations


__all__ = [
    'ExpressionEnvelope',
    'ExpressionsScope',
    'ExpressionsManager',
    'FormattingResult',
]

from typing import Any, Literal, TypeAlias, overload
from dataclasses import field, dataclass
from types import MappingProxyType
from itertools import chain
from collections.abc import Mapping, Callable, Iterable, Generator

from .syntax import Call, StringWithCalls, call_decoder
from .category import ExpressionsCategory
from .definition import Expression, ExpressionDefinition, extract_expression_definition
from .exceptions import ExpressionError, ExpressionExecutionError
from .call_context import ExpressionContext


_ContextTree: TypeAlias = dict[type[ExpressionContext], '_ContextTree']
_CategoriesTree: TypeAlias = dict[str, '_CategoriesTree']
_ExpressionsByCategory: TypeAlias = dict[str | None, dict[str, 'ExpressionEnvelope']]


@dataclass(frozen=True)
class ExpressionEnvelope:
    expression: ExpressionDefinition
    call_key: str
    category: str | None = None


class ExpressionsScope:
    def __init__(self, context_type: type[ExpressionContext]) -> None:
        self._context_type = context_type
        self._parent: ExpressionsScope | None = None
        self._subscopes: dict[type[ExpressionContext], ExpressionsScope] = {}
        self._subscopes_proxy = MappingProxyType(self._subscopes)
        self._expressions: dict[str, ExpressionEnvelope] = {}
        self._expressions_by_category: _ExpressionsByCategory = {}

    def _add_expressions(self, expressions: Iterable[ExpressionEnvelope], /) -> None:
        for expr in expressions:
            self._expressions[expr.call_key] = expr
            if expr.category not in self._expressions_by_category:
                self._expressions_by_category[expr.category] = {}
            self._expressions_by_category[expr.category][expr.call_key] = expr

    def _add_subscope(self, subscope: ExpressionsScope) -> None:
        self._subscopes[subscope._context_type] = subscope
        subscope._parent = self

    @property
    def context_type(self) -> type[ExpressionContext]:
        return self._context_type

    @property
    def parent(self) -> ExpressionsScope | None:
        return self._parent

    @property
    def subscopes(self) -> Mapping[type[ExpressionContext], ExpressionsScope]:
        return self._subscopes_proxy

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


@dataclass(frozen=True)
class FormattingResult:
    result_text: str
    decoded: StringWithCalls
    errors: list[ExpressionError] = field(default_factory=list)

    def __str__(self) -> str:
        return self.result_text


class ExpressionsManager:
    def __init__(self, context: Mapping[str, Any]) -> None:
        self._expressions: dict[type[ExpressionContext], dict[str, ExpressionEnvelope]] = {}
        self._categories: dict[str, ExpressionsCategory] = {}

        self._context_type_to_id: dict[type[ExpressionContext], str] = {}
        self._id_to_context_type: dict[str, type[ExpressionContext]] = {}

        self._categories_tree: dict[Any, Any] = {}
        self._scope_tree: ExpressionsScope = ExpressionsScope(ExpressionContext)

        self._frozen = False
        self._context = context

    @property
    def frozen(self) -> bool:
        return self._frozen

    def get(self, context: type[ExpressionContext]) -> ExpressionsScope:
        self._check_frozen()
        curr = self._scope_tree
        for i in context.get_available_context_types()[1:]:
            if i not in curr.subscopes:
                raise ValueError(
                    f'{context.__module__}.{context.__qualname__} does not exist in scopes tree.'
                )
            curr = curr.subscopes[i]
        return curr

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

        expression = (
            expression
            if isinstance(expression, ExpressionDefinition)
            else extract_expression_definition(expression)
        )
        if not isinstance(context_type, type) or not issubclass(context_type, ExpressionContext):
            raise TypeError('`context_type` must be a subclass of `ExpressionContext`.')

        if context_type not in self._expressions:
            self._expressions[context_type] = {}

        if call_key in self._expressions[context_type]:
            raise ValueError(
                f'Call key {call_key!r} already registered in {context_type.__qualname__} context.'
            )

        self._expressions[context_type][call_key] = ExpressionEnvelope(
            call_key=call_key, category=category, expression=expression
        )

    def register[T: Expression | ExpressionDefinition](
        self,
        *,
        context_type: type[ExpressionContext],
        call_key: str,
        category: str | None = None,
    ) -> Callable[[T], T]:
        def inner(expr: T) -> T:
            self.add_expression(
                expression=expr,
                context_type=context_type,
                call_key=call_key,
                category=category,
            )
            return expr

        return inner

    def add_category(self) -> None:
        self._check_not_frozen()

    def freeze(self) -> None:
        if self._frozen:
            return

        self._check_all_context_types_are_registered()
        self._scope_tree = self._build_scopes_tree()
        self._categories_tree = self._build_categories_tree()
        self._frozen = True

    async def format_string(
        self,
        string: str,
        context: ExpressionContext,
        ignore_errors: bool = False,
    ) -> FormattingResult:
        decoded = call_decoder.extract_calls(string)
        if not decoded.call_spans:
            return FormattingResult(decoded=decoded, result_text=string, errors=[])

        result = []
        errors: list[ExpressionError] = []

        for i in decoded.decoded:
            if isinstance(i, str):
                result.append(i)
                continue

            try:
                result.append(await self.execute_call(i, context, render=True))
            except Exception as err:
                if not isinstance(err, ExpressionExecutionError):
                    new_e = ExpressionExecutionError(expression_id=i.name)
                    new_e.__cause__ = err
                    err = new_e
                if ignore_errors:
                    errors.append(err)
                    continue
                raise err

        return FormattingResult(
            result_text=''.join(result),
            errors=errors,
            decoded=decoded,
        )

    @overload
    async def execute_call(self, call: Call, ctx: ExpressionContext, render: Literal[True]) -> str:
        pass

    @overload
    async def execute_call(self, call: Call, ctx: ExpressionContext, render: bool = False) -> Any:
        pass

    async def execute_call(self, call: Call, ctx: ExpressionContext, render: bool = False) -> Any:
        scope = self.get(type(ctx))
        expr = scope.available_expressions.get(call.name)
        if expr is None:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'Formatter {call.name!r} does not exist in manager.',
            )

        args = [await self.resolve_value(arg, ctx) for arg in call.args]
        kwargs = {key: await self.resolve_value(value, ctx) for key, value in call.kwargs.items()}

        try:
            return await expr.expression.execute(args, kwargs, ctx, self._context, render=render)
        except Exception as e:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'An error occurred while executing {call.name!r}.',
            ) from e

    async def resolve_value(self, value: Any, context: ExpressionContext) -> Any:
        if isinstance(value, Call):
            return await self.execute_call(value, context, render=False)

        if isinstance(value, tuple):
            return tuple([await self.resolve_value(item, context) for item in value])

        if isinstance(value, frozendict):
            return frozendict(
                {key: await self.resolve_value(item, context) for key, item in value.items()}
            )

        return value

    def _check_not_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError(
                'This operation available only when expressions manager is not frozen.'
            )

    def _check_frozen(self) -> None:
        if not self._frozen:
            raise RuntimeError('This operation available only when expressions manager is frozen.')

    def _build_context_tree(self) -> _ContextTree:
        result: _ContextTree = {ExpressionContext: {}}
        for context_type in chain(self._expressions, self._context_type_to_id):
            curr = result
            for curr_context_type in context_type.get_available_context_types():
                if curr_context_type not in curr:
                    curr[curr_context_type] = {}
                curr = curr[curr_context_type]
        return result

    def _build_categories_tree(self) -> _CategoriesTree:
        result: _CategoriesTree = {}
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

    def _build_scopes_tree(
        self, tree: _ContextTree | None = None, attach_to: ExpressionsScope | None = None
    ) -> ExpressionsScope:
        tree = self._build_context_tree()[ExpressionContext] if tree is None else tree
        if attach_to is None:
            attach_to = ExpressionsScope(ExpressionContext)
            expressions = self._expressions.get(ExpressionContext, {})
            attach_to._add_expressions(expressions.values())

        for context_type in tree:
            subscope = ExpressionsScope(context_type)
            expressions = self._expressions.get(context_type, {})
            subscope._add_expressions(expressions.values())
            attach_to._add_subscope(self._build_scopes_tree(tree[context_type], subscope))
        return attach_to

    def _copy(self) -> ExpressionsManager:
        manager = ExpressionsManager({})
        manager._expressions = {k: v.copy() for k, v in self._expressions.items()}
        manager._categories = self._categories.copy()
        manager._context_type_to_id = self._context_type_to_id.copy()
        manager._id_to_context_type = self._id_to_context_type.copy()
        return manager

    def _merge_single(self, manager: ExpressionsManager, skip_existing: bool = True) -> None:
        self._check_not_frozen()
        if not skip_existing:
            for ctx_type in manager._expressions:
                self_exprs = self._expressions.get(ctx_type, {})
                if self_exprs and (
                    collision := self_exprs.keys() & manager._expressions[ctx_type].keys()
                ):
                    raise RuntimeError(f'Expressions {collision!r} already registered.')

            if collision := self._categories.keys() & manager._categories.keys():
                raise RuntimeError(f'Categories {collision!r} already registered.')

            if collision := self._context_type_to_id.keys() & manager._context_type_to_id.keys():
                raise RuntimeError(f'Context types {collision!r} already registered.')

            if collision := self._id_to_context_type.keys() & manager._id_to_context_type.keys():
                raise RuntimeError(f'Context type IDs {collision} already registered.')

        for ctx_type in manager._expressions:
            if ctx_type not in self._expressions:
                self._expressions[ctx_type] = {}

            self._expressions[ctx_type] |= {
                k: v
                for k, v in manager._expressions[ctx_type].items()
                if k not in self._expressions[ctx_type]
            }
        self._categories |= {
            k: v for k, v in manager._categories.items() if k not in self._categories
        }

        id_to_merge = {k for k in manager._id_to_context_type if k not in self._id_to_context_type}
        context_types_to_merge = {
            k: v
            for k, v in manager._context_type_to_id.items()
            if k not in self._context_type_to_id and v in id_to_merge
        }
        self._context_type_to_id |= context_types_to_merge
        self._id_to_context_type |= {v: k for k, v in context_types_to_merge.items()}

    def _replace_with(self, manager: ExpressionsManager) -> None:
        self._check_not_frozen()
        self._expressions = manager._expressions
        self._categories = manager._categories
        self._context_type_to_id = manager._context_type_to_id
        self._id_to_context_type = manager._id_to_context_type

    def merge_from(self, *managers: ExpressionsManager, skip_existing: bool = True) -> None:
        self._check_not_frozen()
        if not managers:
            return

        candidate = self._copy()
        for manager in managers:
            candidate._merge_single(manager, skip_existing=skip_existing)

        self._replace_with(candidate)
