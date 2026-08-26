from __future__ import annotations

import inspect
from typing import (
    Any,
    Literal,
    TypeVar,
    Protocol,
    Sequence,
    ParamSpec,
    overload,
    runtime_checkable,
)
from dataclasses import field, dataclass
from functools import cache
from collections import defaultdict
from collections.abc import Mapping, Callable, Iterator

from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.expressions.syntax import Call, StringWithCalls
from hubplatform.expressions.syntax.parsing import call_decoder

from .call_context import ExpressionCallContext


_P = ParamSpec('_P', default=...)


@runtime_checkable
class ExpressionProto(Protocol[_P]):
    async def __call__(self, _c: ExpressionCallContext, /, *_a: _P.args, **_kw: _P.kwargs) -> Any:
        pass


@runtime_checkable
class ExpressionWithRendererProto(ExpressionProto[_P], Protocol[_P]):
    async def render(
        self, _c: ExpressionCallContext, _v: Any, /, *_a: _P.args, **_kw: _P.kwargs
    ) -> str:
        pass


type Expression = ExpressionProto | type[ExpressionProto]


class ExpressionError(Exception):
    def __init__(self, expression_id: str, message: str | None = None) -> None:
        if message is None:
            message = f'An unexpected error occurred while executing expression {expression_id!r}.'
        self.expression_id = expression_id
        super().__init__(message)


@dataclass
class ExpressionDoc:
    overview: str
    args_doc: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpressionEnvelope:
    id: str
    name: str
    description: ExpressionDoc
    supported_contexts: tuple[type[ExpressionCallContext], ...]
    call: Expression
    _wrapped: CallableWrapper[str] = field(init=False)
    _wrapped_init: CallableWrapper[None] | None = field(init=False, default=None)
    _wrapped_render: CallableWrapper[str] | None = field(init=False, default=None)
    _is_class: bool = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.call, type):
            object.__setattr__(self, '_is_class', True)
            object.__setattr__(self, '_wrapped', CallableWrapper(self.call.__call__))
            object.__setattr__(self, '_wrapped_init', CallableWrapper(self.call.__init__))
            if hasattr(self.call, 'render') and inspect.iscoroutinefunction(self.call.render):
                object.__setattr__(self, '_wrapped_render', CallableWrapper(self.call.render))
        else:
            object.__setattr__(self, '_is_class', False)
            object.__setattr__(self, '_wrapped', CallableWrapper(self.call))

    @overload
    async def execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: Literal[True],
    ) -> str:
        pass

    @overload
    async def execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool = False,
    ) -> Any:
        pass

    async def execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool = False,
    ) -> str:
        try:
            result = await self._execute(call, context, di_context, render=render)
        except ExpressionError:
            raise
        except Exception as e:
            raise ExpressionError(
                expression_id=call.name,
                message=f'An unexpected error occurred while executing expression {call.name!r}.',
            ) from e

        if not isinstance(result, str):
            raise ExpressionError(
                expression_id=call.name,
                message=f'Expression {call.name!r} returned a non-string value.',
            )
        return result

    @overload
    async def _execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: Literal[True],
    ) -> str:
        pass

    @overload
    async def _execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: Literal[False],
    ) -> Any:
        pass

    @overload
    async def _execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool,
    ) -> str | Any:
        pass

    async def _execute(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool,
    ) -> str:
        if self._is_class:
            instance = object.__new__(self.call)
            call_args, call_kwargs = self._wrapped_init.collect_args(
                args=[instance, *call.args], kwargs=call.kwargs
            )
            self.call.__init__(*call_args, **call_kwargs)
            result = await self._wrapped(
                args=[instance, context], data=di_context, to_thread=False
            )
            if render:
                if self._wrapped_render is None:
                    return str(result)
                return await self._wrapped_render(
                    args=[instance, result, context], data=di_context, to_thread=False
                )
        return await self._wrapped(
            args=[context, *call.args], data={**call.kwargs, **di_context}, to_thread=False
        )

    def check_can_be_included(self, category: ExpressionsCategory) -> None:
        for context in category.supported_contexts:
            if not issubclass(context, self.supported_contexts):
                raise ValueError(
                    f'Expression {self.id!r} cannot be included into category '
                    f'{category.id!r}: context {context.__name__!r} '
                    f'is not supported by the expression.'
                )


@dataclass(frozen=True)
class ExpressionsCategory:
    id: str
    name: str
    description: str
    supported_contexts: tuple[type[ExpressionCallContext], ...]

    def check_can_include_category(self, subcategory: ExpressionsCategory) -> None:
        for context in self.supported_contexts:
            if not issubclass(context, subcategory.supported_contexts):
                raise ValueError(
                    f'ExpressionsCategory {self.id!r} cannot include category '
                    f'{subcategory.id!r}: context {context.__name__!r} '
                    f'is not supported by the included category.'
                )

    def check_can_include_expression(self, expression: ExpressionEnvelope) -> None:
        for context in self.supported_contexts:
            if not issubclass(context, expression.supported_contexts):
                raise ValueError(
                    f'ExpressionsCategory {self.id!r} cannot include expression '
                    f'{expression.id!r}: context {context.__name__!r} '
                    f'is not supported by the included expression.'
                )

    def check_can_be_included(self, category: ExpressionsCategory) -> None:
        for context in category.supported_contexts:
            if not issubclass(context, self.supported_contexts):
                raise ValueError(
                    f'ExpressionsCategory {self.id!r} cannot be included into category '
                    f'{category.id!r}: context {context.__name__!r} '
                    f'is not supported by current category.'
                )


@dataclass(frozen=True)
class FormattingResult:
    result_text: str
    decoded: StringWithCalls
    errors: list[ExpressionError] = field(default_factory=list)

    def __str__(self) -> str:
        return self.result_text


_F = TypeVar('_F', bound=Expression)


class ExpressionsRegistry:
    def __init__(self) -> None:
        self._expressions: dict[str, ExpressionEnvelope] = {}
        self._categories: dict[str, ExpressionsCategory] = {}

        self._included_categories: dict[str, set[str]] = defaultdict(set)
        self._included_expressions: dict[str, set[str]] = defaultdict(set)

    def merge_from(self, *registries: ExpressionsRegistry, skip_existing: bool = True) -> None:
        if not registries:
            return

        candidate = self._copy()
        for registry in registries:
            candidate._merge_single(registry, skip_existing=skip_existing)

        candidate._validate_inclusions()
        self._replace_with(candidate)

    def _merge_single(self, registry: ExpressionsRegistry, skip_existing: bool = True) -> None:
        if not skip_existing:
            if collision := self._expressions.keys() & registry._expressions.keys():
                raise RuntimeError(f'Expressions {collision!r} already registered.')
            if collision := self._categories.keys() & registry._categories.keys():
                raise RuntimeError(f'Categories {collision!r} already registered.')

        self._expressions |= {
            k: v for k, v in registry._expressions.items() if k not in self._expressions
        }
        self._categories |= {
            k: v for k, v in registry._categories.items() if k not in self._categories
        }

        for id, included_categories in registry._included_categories.items():
            self._included_categories[id].update(included_categories)
        for id, included_expressions in registry._included_expressions.items():
            self._included_expressions[id].update(included_expressions)

    def _copy(self) -> ExpressionsRegistry:
        result = ExpressionsRegistry()
        result._expressions = self._expressions.copy()
        result._categories = self._categories.copy()
        result._included_categories = defaultdict(
            set,
            {
                category_id: included_ids.copy()
                for category_id, included_ids in self._included_categories.items()
            },
        )
        result._included_expressions = defaultdict(
            set,
            {
                category_id: expression_ids.copy()
                for category_id, expression_ids in self._included_expressions.items()
            },
        )
        return result

    def _replace_with(self, registry: ExpressionsRegistry) -> None:
        self._expressions = registry._expressions
        self._categories = registry._categories
        self._included_categories = registry._included_categories
        self._included_expressions = registry._included_expressions

    def _validate_inclusions(self) -> None:
        self._validate_category_inclusions_are_acyclic()

        for category_id, expression_ids in self._included_expressions.items():
            category = self._categories.get(category_id)
            if category is None:
                continue

            for expression_id in expression_ids:
                expression = self._expressions.get(expression_id)
                if expression is not None:
                    category.check_can_include_expression(expression)

        for category_id, included_ids in self._included_categories.items():
            category = self._categories.get(category_id)
            if category is None:
                continue

            for included_id in included_ids:
                included_category = self._categories.get(included_id)
                if included_category is not None:
                    category.check_can_include_category(included_category)

    def _validate_category_inclusions_are_acyclic(self) -> None:
        visited: set[str] = set()

        for root_id in self._included_categories:
            if root_id in visited:
                continue

            path = [root_id]
            active_positions = {root_id: 0}
            stack: list[tuple[str, Iterator[str]]] = [
                (root_id, iter(sorted(self._included_categories.get(root_id, ()))))
            ]

            while stack:
                category_id, included_ids = stack[-1]
                try:
                    included_id = next(included_ids)
                except StopIteration:
                    stack.pop()
                    path.pop()
                    active_positions.pop(category_id)
                    visited.add(category_id)
                    continue

                if included_id in active_positions:
                    cycle_start = active_positions[included_id]
                    cycle = [*path[cycle_start:], included_id]
                    cycle_path = ' -> '.join(repr(item) for item in cycle)
                    raise ValueError(
                        f'ExpressionsCategory inclusion cycle detected: {cycle_path}.'
                    )

                if included_id in visited:
                    continue

                active_positions[included_id] = len(path)
                path.append(included_id)
                stack.append(
                    (
                        included_id,
                        iter(sorted(self._included_categories.get(included_id, ()))),
                    )
                )

    @overload
    def add_expression(
        self,
        expression: _F,
        *,
        id: str,
        name: str,
        description: str,
        supported_contexts: tuple[type[ExpressionCallContext], ...],
    ) -> _F:
        pass

    @overload
    def add_expression(
        self,
        expression: None = None,
        *,
        id: str,
        name: str,
        description: str,
        supported_contexts: tuple[type[ExpressionCallContext], ...],
    ) -> Callable[[_F], _F]:
        pass

    def add_expression(
        self,
        expression: _F | None = None,
        *,
        id: str,
        name: str,
        description: str | ExpressionDoc,
        supported_contexts: tuple[type[ExpressionCallContext], ...],
    ) -> Callable[[_F], _F] | _F:
        def inner(expression: _F) -> _F:
            if id in self._expressions:
                raise RuntimeError(f'Formatter {id} already registered.')
            envelope = ExpressionEnvelope(
                id=id,
                name=name,
                description=description
                if isinstance(description, ExpressionDoc)
                else ExpressionDoc(overview=description),
                call=expression,
                supported_contexts=supported_contexts,
            )

            candidate = self._copy()
            candidate._expressions[id] = envelope
            candidate._validate_inclusions()
            self._replace_with(candidate)
            return expression

        if expression is None:
            return inner
        return inner(expression)

    def add_category(
        self,
        id: str,
        name: str,
        description: str,
        include_expressions: Sequence[str],
        include_categories: Sequence[str],
        supported_contexts: tuple[type[ExpressionCallContext], ...],
    ) -> None:
        if id in self._categories:
            raise RuntimeError(f'ExpressionsCategory {id} already registered.')

        category = ExpressionsCategory(
            id=id,
            name=name,
            description=description,
            supported_contexts=supported_contexts,
        )

        candidate = self._copy()
        candidate._categories[id] = category
        if include_expressions:
            candidate._included_expressions[id].update(include_expressions)
        if include_categories:
            candidate._included_categories[id].update(include_categories)
        candidate._validate_inclusions()
        self._replace_with(candidate)

    def include_expressions_in_category(self, category_id: str, *expression_ids: str) -> None:
        if not expression_ids:
            return

        candidate = self._copy()
        candidate._included_expressions[category_id].update(expression_ids)
        candidate._validate_inclusions()
        self._replace_with(candidate)

    def include_categories_in_category(self, category_id: str, *include_ids: str) -> None:
        if not include_ids:
            return

        candidate = self._copy()
        candidate._included_categories[category_id].update(include_ids)
        candidate._validate_inclusions()
        self._replace_with(candidate)

    def get_category_expressions(
        self,
        category_id: str,
        expand_categories: bool = False,
        existing_expressions_only: bool = True,
        existing_categories_only: bool = True,
    ) -> dict[str, ExpressionEnvelope]:
        if existing_categories_only and category_id not in self._categories:
            return {}

        included_expressions = self._included_expressions.get(category_id, set())
        result = {}
        for i in included_expressions:
            if existing_expressions_only and i not in self._expressions:
                continue
            result[i] = self._expressions.get(i)

        if expand_categories and self._included_categories.get(category_id):
            for subcat in self._included_categories.get(category_id, set()):
                result.update(
                    self.get_category_expressions(
                        subcat,
                        expand_categories=expand_categories,
                        existing_expressions_only=existing_expressions_only,
                        existing_categories_only=existing_categories_only,
                    )
                )
        return result

    async def format_text(
        self,
        string: str,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        ignore_errors: bool = False,
    ) -> FormattingResult:
        decoded = call_decoder.extract_calls(string)
        if not decoded.call_spans:
            return FormattingResult(decoded=decoded, result_text=string, errors=[])

        errors: list[ExpressionError] = []

        result = []
        for i in decoded.decoded:
            if isinstance(i, str):
                result.append(i)
                continue

            try:
                result.append(await self.execute_call(i, context, di_context, render=True))
            except Exception as err:
                if not isinstance(err, ExpressionError):
                    new_e = ExpressionError(expression_id=i.name)
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

    async def resolve_value(
        self, value: Any, context: ExpressionCallContext, di_context: Mapping[str, Any]
    ) -> Any:
        if isinstance(value, Call):
            return await self.execute_call(value, context, di_context)

        if isinstance(value, list):
            return [await self.resolve_value(item, context, di_context) for item in value]

        if isinstance(value, dict):
            return {
                key: await self.resolve_value(item, context, di_context)
                for key, item in value.items()
            }

        return value

    @overload
    async def execute_call(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: Literal[True],
    ) -> str:
        pass

    @overload
    async def execute_call(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool = False,
    ) -> Any:
        pass

    async def execute_call(
        self,
        call: Call,
        context: ExpressionCallContext,
        di_context: Mapping[str, Any],
        render: bool = False,
    ) -> Any:
        expression = self._expressions.get(call.name)
        if expression is None:
            raise ExpressionError(
                expression_id=call.name,
                message=f'Formatter {call.name!r} does not exist in registry.',
            )

        args = [await self.resolve_value(arg, context, di_context) for arg in call.args]

        kwargs = {
            key: await self.resolve_value(value, context, di_context)
            for key, value in call.kwargs.items()
        }

        resolved_call = Call(name=call.name, args=args, kwargs=kwargs)
        return await expression.execute(resolved_call, context, di_context, render=render)


@cache
def global_expressions_registry() -> ExpressionsRegistry:
    return ExpressionsRegistry()
