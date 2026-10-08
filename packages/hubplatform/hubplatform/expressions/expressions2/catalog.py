"""Namespaced implementation definitions, independent of template aliases.

The catalog answers: "Which implementation is ``funpay.order``?" A scope
answers: "What does ``$order`` mean in this template?" Keeping those questions
separate permits two marketplaces to expose the same template vocabulary.
"""

from __future__ import annotations

import re
import inspect
from typing import Any
from dataclasses import field, dataclass
from types import MappingProxyType
from collections.abc import Mapping, Callable, Sequence

from .errors import (
    ExpressionError,
    ExpressionsFrozenError,
    ExpressionArgumentError,
    ExpressionConfigurationError,
)
from .capabilities import Capability, EvaluationContext, validate_id


type ExpressionCallback = Callable[..., Any]
type Renderer = Callable[[EvaluationContext, Any], Any]


def validate_alias(alias: str) -> None:
    """Keep template names compatible with the existing call parser."""
    if not isinstance(alias, str) or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', alias) is None:
        raise ExpressionConfigurationError(
            f'Invalid template name {alias!r}; use ASCII letters, digits, and underscores.'
        )


@dataclass(frozen=True)
class ExpressionDefinition:
    """One implementation, its dependency contract, and display metadata.

    Callbacks receive EvaluationContext first. User arguments follow it;
    injected capabilities occupy declared keyword-only parameters. For example:

        @catalog.expression('stars.amount', requires={'order': ORDER_REFERENCE})
        async def amount(ctx: EvaluationContext, *, order: OrderReference) -> int:
            ...

    ``requires`` is both setup metadata and an injection plan. A template cannot
    override these parameters. Services can be captured at plugin setup or read
    from ``ctx.services``; their names are never merged with template arguments.

    A renderer receives ``(ctx, raw_value)`` and must return str. Nested calls
    use raw values and skip renderers. Ordinary callable instances are supported;
    initialize them explicitly instead of registering a class constructor.
    """

    id: str
    callback: ExpressionCallback
    requires: Mapping[str, Capability[Any]] = field(default_factory=dict)
    renderer: Renderer | None = None
    name: str = ''
    description: str = ''
    category: str | None = None
    _signature: inspect.Signature = field(init=False, repr=False, compare=False)
    _context_parameter: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        validate_id(self.id, 'Expression')
        if not callable(self.callback) or inspect.isclass(self.callback):
            raise ExpressionConfigurationError(
                f'Expression {self.id!r} must be a function or an initialized callable object.'
            )
        try:
            signature = inspect.signature(self.callback)
        except (TypeError, ValueError) as exc:
            raise ExpressionConfigurationError(
                f'Cannot inspect the callback for expression {self.id!r}.'
            ) from exc
        parameters = list(signature.parameters.values())
        if not parameters or parameters[0].kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise ExpressionConfigurationError(
                f'Expression {self.id!r} needs an explicit first evaluation-context parameter.'
            )

        dependencies = dict(self.requires)
        for parameter, capability in dependencies.items():
            declaration = signature.parameters.get(parameter)
            if declaration is None or declaration.kind != inspect.Parameter.KEYWORD_ONLY:
                raise ExpressionConfigurationError(
                    f'Injected parameter {parameter!r} of {self.id!r} must be keyword-only.'
                )
            if not isinstance(capability, Capability):
                raise ExpressionConfigurationError(
                    f'Requirement {parameter!r} of {self.id!r} must be a Capability.'
                )

        if self.renderer is not None:
            if not callable(self.renderer) or inspect.isclass(self.renderer):
                raise ExpressionConfigurationError(f'Invalid renderer for {self.id!r}.')
            try:
                inspect.signature(self.renderer).bind(object(), object())
            except (TypeError, ValueError) as exc:
                raise ExpressionConfigurationError(
                    f'Renderer for {self.id!r} must accept (context, value).'
                ) from exc

        # Copy registration mappings. Mutating a plugin's original dict after
        # freeze must not silently change a compiled scope's requirements.
        object.__setattr__(self, 'requires', MappingProxyType(dependencies))
        object.__setattr__(self, '_signature', signature)
        object.__setattr__(self, '_context_parameter', parameters[0].name)

    @property
    def capabilities(self) -> frozenset[Capability[Any]]:
        """Contracts required to execute this definition in a scope."""
        return frozenset(self.requires.values())

    async def evaluate(
        self, ctx: EvaluationContext, args: Sequence[Any], kwargs: Mapping[str, Any]
    ) -> Any:
        """Bind public arguments and dependencies, then return the raw value."""
        reserved = set(self.requires) | {self._context_parameter}
        if forbidden := reserved.intersection(kwargs):
            raise ExpressionArgumentError(
                f'Expression {self.id!r} reserves injected parameters {sorted(forbidden)!r}.',
                expression_id=self.id,
            )
        injected = {name: ctx.require(key) for name, key in self.requires.items()}
        try:
            bound = self._signature.bind(ctx, *args, **kwargs, **injected)
        except TypeError as exc:
            raise ExpressionArgumentError(
                f'Invalid arguments for expression {self.id!r}: {exc}', expression_id=self.id
            ) from exc
        result = self.callback(*bound.args, **bound.kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def render(self, ctx: EvaluationContext, value: Any) -> str:
        """Convert a top-level result to text without changing nested values."""
        if self.renderer is None:
            return str(value)
        rendered = self.renderer(ctx, value)
        if inspect.isawaitable(rendered):
            rendered = await rendered
        if not isinstance(rendered, str):
            raise ExpressionError(
                f'Renderer for {self.id!r} returned {type(rendered).__name__}, expected str.',
                expression_id=self.id,
            )
        return rendered


class ExpressionCatalog:
    """Application-owned definitions indexed by unique internal IDs.

    There is no process-global singleton. Components and plugins receive the
    application's catalog during setup. Two HubPlatformApp instances therefore
    cannot accidentally retain each other's installed expressions.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, ExpressionDefinition] = {}
        self._frozen = False

    @property
    def definitions(self) -> Mapping[str, ExpressionDefinition]:
        """All registered implementations, including definitions not yet bound."""
        return MappingProxyType(self._definitions)

    def add(self, definition: ExpressionDefinition) -> None:
        """Register a definition; duplicate implementation IDs are always errors."""
        if self._frozen:
            raise ExpressionsFrozenError('Expression catalog is frozen.')
        if definition.id in self._definitions:
            raise ExpressionConfigurationError(f'Expression {definition.id!r} already exists.')
        self._definitions[definition.id] = definition

    def expression[F: ExpressionCallback](
        self,
        id: str,
        *,
        requires: Mapping[str, Capability[Any]] | None = None,
        renderer: Renderer | None = None,
        name: str = '',
        description: str = '',
        category: str | None = None,
    ) -> Callable[[F], F]:
        """Decorator that preserves the original callback for ordinary Python use."""

        def register(callback: F) -> F:
            self.add(
                ExpressionDefinition(
                    id=id,
                    callback=callback,
                    requires=requires or {},
                    renderer=renderer,
                    name=name,
                    description=description,
                    category=category,
                )
            )
            return callback

        return register

    def freeze(self) -> None:
        """Seal definitions after the manager has successfully compiled scopes."""
        self._frozen = True
