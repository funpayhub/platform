from __future__ import annotations

from typing import TYPE_CHECKING
from collections.abc import Sequence

from hubplatform.exceptions import HubPlatformError


if TYPE_CHECKING:
    from .traits import Trait
    from .manager.envelope import ExpressionEnvelope


class ExpressionError(HubPlatformError): ...


class ExpressionExecutionError(ExpressionError):
    def __init__(self, expression_id: str, message: str | None = None) -> None:
        if message is None:
            message = f'An unexpected error occurred while executing expression {expression_id!r}.'
        self.expression_id = expression_id
        super().__init__(message)


class UnknownExpressionError(ExpressionExecutionError):
    """There is no expression with this name for the traits the text is evaluated with."""

    def __init__(self, expression_id: str) -> None:
        super().__init__(
            expression_id,
            f'Expression {expression_id!r} is not available for these traits.',
        )


class AmbiguousExpressionError(ExpressionExecutionError):
    """Several expressions with this name are available for the traits the text is evaluated
    with, and none of them is more specific than all the others."""

    def __init__(self, expression_id: str, candidates: Sequence[ExpressionEnvelope]) -> None:
        self.candidates = tuple(candidates)
        requirements = ', '.join(repr(i.requirement) for i in self.candidates)
        super().__init__(
            expression_id,
            f'Expression {expression_id!r} is ambiguous for these traits: it is registered for '
            f'{requirements}, and none of them is more specific than the others. Register an '
            f'override that requires the traits of all of them.',
        )


class UndeclaredTraitError(ExpressionError, LookupError):
    """An expression asked for a trait that it did not declare in its requirement."""

    def __init__(self, trait_type: type[Trait], declared: Sequence[type[Trait]]) -> None:
        self.trait_type = trait_type
        self.declared = tuple(declared)
        names = ', '.join(i.__qualname__ for i in self.declared) or 'nothing'
        super().__init__(
            f'{trait_type.__qualname__} is not declared by the expression (it declares {names}).'
        )


class ExpressionsConfigurationError(ExpressionError):
    """Registered expressions conflict with each other.

    Raised by ``ExpressionsManager.freeze()``.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__('\n'.join(['Expressions are configured incorrectly:', *self.problems]))
