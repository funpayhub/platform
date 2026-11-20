from __future__ import annotations


__all__ = [
    'ExpressionDefinition',
    'ExpressionCallResult',
    'ExpressionRenderer',
    'Expression',
    'expression',
    'extract_expression_definition',
]

import inspect
import functools
from typing import Any, Protocol, Sequence, ParamSpec, runtime_checkable
from dataclasses import field, dataclass
from collections.abc import Mapping, Callable, Awaitable

from eventry.asyncio.callable_wrappers import CallableWrapper

from .docs import ExpressionDocs
from .traits import TraitsContainer
from .fragments import Fragment, EvaluatedPart
from .requirement import Requirement, RequirementLike


_P = ParamSpec('_P')


@runtime_checkable
class ExpressionProto(Protocol[_P]):
    async def __call__(self, _c: TraitsContainer, /, *_a: _P.args, **_kw: _P.kwargs) -> Any:
        pass


@runtime_checkable
class ExpressionWithRendererProto(ExpressionProto[_P], Protocol[_P]):
    async def render(
        self, _c: TraitsContainer, _v: Any, /, *_a: _P.args, **_kw: _P.kwargs
    ) -> str | Fragment:
        pass


type Expression = ExpressionProto[Any] | type[ExpressionProto[Any]]


@dataclass(frozen=True)
class ExpressionDefinition:
    call: Expression
    docs: ExpressionDocs
    requirement: Requirement = field(default_factory=Requirement)
    """Trait types a container must have for the expression to be available. The expression
    receives a view of the container that answers only for these types."""
    _wrapped: CallableWrapper[str] = field(init=False)
    _wrapped_init: CallableWrapper[None] | None = field(init=False, default=None)
    _wrapped_renderer: CallableWrapper[str | Fragment] | None = field(init=False, default=None)
    _is_class: bool = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.docs, ExpressionDocs):
            raise TypeError(
                f'Expression docs must be an instance of `ExpressionDocs`, not {type(self.docs)}.'
            )
        if not isinstance(self.requirement, Requirement):
            raise TypeError(
                f'Expression requirement must be an instance of `Requirement`, '
                f'not {type(self.requirement)}.'
            )
        if isinstance(self.call, type):
            object.__setattr__(self, '_is_class', True)
            object.__setattr__(self, '_wrapped', CallableWrapper(self.call.__call__))
            object.__setattr__(self, '_wrapped_init', CallableWrapper(self.call.__init__))
            if hasattr(self.call, 'render') and inspect.iscoroutinefunction(self.call.render):
                object.__setattr__(self, '_wrapped_renderer', CallableWrapper(self.call.render))
        else:
            object.__setattr__(self, '_is_class', False)
            object.__setattr__(self, '_wrapped', CallableWrapper(self.call))

    async def execute(
        self,
        traits: TraitsContainer,
        args: Sequence[Any],
        kwargs: Mapping[str, Any],
        di: Mapping[str, Any],
    ) -> ExpressionCallResult:
        """Calls the expression once and returns its raw result.

        The expression and its renderer receive a view of ``traits`` that answers only for the
        trait types of ``requirement``.
        """
        view = traits.view(self.requirement.traits)
        instance: Any = None
        if self._is_class and self._wrapped_init is not None:
            instance = object.__new__(self.call)  # type: ignore[arg-type]
            call_args, call_kwargs = self._wrapped_init.collect_args(
                args=[instance, *args], kwargs=kwargs
            )
            self.call.__init__(*call_args, **call_kwargs)  # type: ignore[misc]
            value = await self._wrapped(args=[instance, view], data=di, to_thread=False)
        else:
            value = await self._wrapped(args=[view, *args], data={**kwargs, **di}, to_thread=False)

        renderer: ExpressionRenderer | None = None
        if self._wrapped_renderer is not None:
            renderer = functools.partial(self._call_renderer, self._wrapped_renderer, instance)
        return ExpressionCallResult(value=value, traits=view, renderer=renderer)

    @staticmethod
    async def _call_renderer(
        wrapped_renderer: CallableWrapper[str | Fragment],
        instance: Any,
        traits: TraitsContainer,
        value: Any,
        di: Mapping[str, Any],
    ) -> Any:
        return await wrapped_renderer(args=[instance, traits, value], data=di, to_thread=False)


type ExpressionRenderer = Callable[[TraitsContainer, Any, Mapping[str, Any]], Awaitable[Any]]
"""
Renders the value of a call: ``renderer(traits, value, di)``.
Must return a string or a ``Fragment``.
"""


@dataclass(frozen=True, slots=True)
class ExpressionCallResult:
    """Raw result of one expression call, with the renderer of the expression that made it."""

    value: Any
    """The value returned by the expression."""

    traits: TraitsContainer
    """The traits the expression was called with. The value is rendered with them too."""

    renderer: ExpressionRenderer | None = None
    """The renderer of the expression, ``None`` if it has no renderer."""

    async def render(self, di: Mapping[str, Any]) -> EvaluatedPart:
        """Converts the value into a part of the evaluated string.

        - With a renderer, its result is used. It must be a string or a ``Fragment``.
        - Without a renderer, a ``Fragment`` is kept as-is and any other value is converted
          with ``str()``.
        """
        if self.renderer is None:
            if isinstance(self.value, Fragment):
                return self.value
            return str(self.value)

        rendered = await self.renderer(self.traits, self.value, di)
        if not isinstance(rendered, (str, Fragment)):
            raise TypeError(
                'Expression renderer must return a string or a `Fragment`, '
                f'not {type(rendered).__name__}.'
            )
        return rendered


def expression[T: Expression](
    *, docs: ExpressionDocs, requires: RequirementLike = ()
) -> Callable[[T], T]:
    """Attaches docs and a requirement to an expression.

    :param requires: Trait types the expression needs: one type or several. Without it, the
        expression is available everywhere and receives an empty view.
    """
    requirement = Requirement.of(requires)

    def inner(expression_obj: T) -> T:
        definition = ExpressionDefinition(
            call=expression_obj,
            docs=docs,
            requirement=requirement,
        )
        setattr(expression_obj, '__hubplatform_expression_definition__', definition)
        return expression_obj

    return inner


def extract_expression_definition(obj: object) -> ExpressionDefinition:
    definition = getattr(obj, '__hubplatform_expression_definition__', None)
    if not isinstance(definition, ExpressionDefinition):
        raise ValueError(f'{obj} was not wrapped with `@expression` decorator.')
    return definition
