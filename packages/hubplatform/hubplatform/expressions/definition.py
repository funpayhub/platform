from __future__ import annotations


__all__ = ['ExpressionDefinition', 'Expression', 'expression', 'extract_expression_definition']

import inspect
from typing import Any, Literal, Protocol, ParamSpec, overload, runtime_checkable
from dataclasses import field, dataclass
from collections.abc import Mapping, Callable

from eventry.asyncio.callable_wrappers import CallableWrapper

from .docs import ExpressionDocs
from .syntax import Call
from .exceptions import ExpressionExecutionError
from .call_context import ExpressionContext


_P = ParamSpec('_P')


@runtime_checkable
class ExpressionProto(Protocol[_P]):
    async def __call__(self, _c: ExpressionContext, /, *_a: _P.args, **_kw: _P.kwargs) -> Any:
        pass


@runtime_checkable
class ExpressionWithRendererProto(ExpressionProto[_P], Protocol[_P]):
    async def render(
        self, _c: ExpressionContext, _v: Any, /, *_a: _P.args, **_kw: _P.kwargs
    ) -> str:
        pass


type Expression = ExpressionProto | type[ExpressionProto]


@dataclass(frozen=True)
class ExpressionDefinition:
    call: Expression
    docs: ExpressionDocs
    _wrapped: CallableWrapper[str] = field(init=False)
    _wrapped_init: CallableWrapper[None] | None = field(init=False, default=None)
    _wrapped_renderer: CallableWrapper[str] | None = field(init=False, default=None)
    _is_class: bool = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.docs, ExpressionDocs):
            raise TypeError(
                f'Expression docs must be an instance of `ExpressionDocs`, not {type(self.docs)}.'
            )
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
        context: ExpressionContext,
        di_mapping: Mapping[str, Any],
        render: Literal[True],
    ) -> str:
        pass

    @overload
    async def execute(
        self,
        call: Call,
        context: ExpressionContext,
        di_mapping: Mapping[str, Any],
        render: bool = False,
    ) -> Any:
        pass

    async def execute(
        self,
        call: Call,
        context: ExpressionContext,
        di_mapping: Mapping[str, Any],
        render: bool = False,
    ) -> Any:
        try:
            return await self._execute(call, context, di_mapping, render=render)
        except ExpressionExecutionError:
            raise
        except Exception as e:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'An unexpected error occurred while executing expression {call.name!r}.',
            ) from e

    async def _execute(
        self, call: Call, context: ExpressionContext, di: Mapping[str, Any], render: bool = False
    ) -> Any:
        instance: Any = None
        if self._is_class and self._wrapped_init is not None:
            instance = object.__new__(self.call)  # type: ignore[arg-type]
            call_args, call_kwargs = self._wrapped_init.collect_args(
                args=[instance, *call.args], kwargs=call.kwargs
            )
            self.call.__init__(*call_args, **call_kwargs)  # type: ignore[misc]
            result = await self._wrapped(args=[instance, context], data=di, to_thread=False)
        else:
            result = await self._wrapped(
                args=[context, *call.args], data={**call.kwargs, **di}, to_thread=False
            )
        if not render:
            return result

        if self._wrapped_renderer is not None:
            return await self._wrapped_renderer(
                args=[instance, context, result], data=di, to_thread=False
            )
        return str(result)


def expression[T: Expression](*, docs: ExpressionDocs) -> Callable[[T], T]:
    def inner(expression_obj: T) -> T:
        definition = ExpressionDefinition(
            call=expression_obj,
            docs=docs,
        )
        expression_obj.__dict__['__hubplatform_expression_definition__'] = definition
        return expression_obj
    return inner


def extract_expression_definition(obj: Any) -> ExpressionDefinition:
    if not hasattr(obj, '__hubplatform_expression_definition__'):
        raise ValueError(f'{obj} was not wrapped with `@expression` decorator.')

    return getattr(obj, '__hubplatform_expression_definition__')
