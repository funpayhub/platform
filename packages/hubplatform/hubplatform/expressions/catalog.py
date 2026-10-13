from __future__ import annotations

import inspect
from types import MappingProxyType
from typing import Any, Literal, Protocol, ParamSpec, overload, runtime_checkable
from dataclasses import field, dataclass
from collections.abc import Mapping, Callable

from eventry.asyncio.callable_wrappers import CallableWrapper

from .syntax import Call
from .exceptions import ExpressionExecutionError


_P = ParamSpec('_P', default=...)


@runtime_checkable
class ExpressionProto(Protocol[_P]):
    async def __call__(self, /, *_a: _P.args, **_kw: _P.kwargs) -> Any:
        pass


@runtime_checkable
class ExpressionWithRendererProto(ExpressionProto[_P], Protocol[_P]):
    async def render(self, _v: Any, /, *_a: _P.args, **_kw: _P.kwargs) -> str:
        pass


type Expression = ExpressionProto | type[ExpressionProto]


@dataclass(frozen=True)
class ExpressionEnvelope:
    id: str
    call: Expression
    _wrapped: CallableWrapper[str] = field(init=False)
    _wrapped_init: CallableWrapper[None] | None = field(init=False, default=None)
    _wrapped_renderer: CallableWrapper[str] | None = field(init=False, default=None)
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
        self, call: Call, di_mapping: Mapping[str, Any], render: Literal[True]
    ) -> str:
        pass

    @overload
    async def execute(
        self, call: Call, di_mapping: Mapping[str, Any], render: bool = False
    ) -> Any:
        pass

    async def execute(
        self, call: Call, di_mapping: Mapping[str, Any], render: bool = False
    ) -> Any:
        try:
            return await self._execute(call, di_mapping, render=render)
        except ExpressionExecutionError:
            raise
        except Exception as e:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'An unexpected error occurred while executing expression {call.name!r}.',
            ) from e

    async def _execute(self, call: Call, di: Mapping[str, Any], render: bool = False) -> Any:
        instance: Any = None
        if self._is_class and self._wrapped_init is not None:
            instance = object.__new__(self.call)  # type: ignore[arg-type]
            call_args, call_kwargs = self._wrapped_init.collect_args(
                args=[instance, *call.args], kwargs=call.kwargs
            )
            self.call.__init__(*call_args, **call_kwargs)  # type: ignore[misc]
            result = await self._wrapped(args=[instance], data=di, to_thread=False)
        else:
            result = await self._wrapped(
                args=[*call.args], data={**call.kwargs, **di}, to_thread=False
            )
        if not render:
            return result

        if self._wrapped_renderer is not None:
            return await self._wrapped_renderer(args=[instance, result], data=di, to_thread=False)
        return str(result)


class ExpressionsCatalog:
    def __init__(self) -> None:
        self._expressions: dict[str, ExpressionEnvelope] = {}

    @property
    def expressions(self) -> Mapping[str, ExpressionEnvelope]:
        return MappingProxyType(self._expressions)

    @overload
    def add_expression[_F](self, expression: _F, *, id: str) -> _F:
        pass

    @overload
    def add_expression[_F](self, expression: None = None, *, id: str) -> Callable[[_F], _F]:
        pass

    def add_expression[_F](
        self,
        expression: _F | None = None,
        *,
        id: str,
    ) -> Callable[[_F], _F] | _F:
        if id in self._expressions:
            raise RuntimeError(f'Expression {id} already registered.')

        def inner(expression: _F) -> _F:
            envelope = ExpressionEnvelope(id=id, call=expression)
            self._expressions[id] = envelope
            return expression

        if expression is None:
            return inner
        return inner(expression)
