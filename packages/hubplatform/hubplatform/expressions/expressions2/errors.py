"""Separate setup errors from errors produced while evaluating a template."""

from __future__ import annotations


class ExpressionsError(Exception):
    """Base error for the new expression subsystem."""


class ExpressionConfigurationError(ExpressionsError):
    """Invalid catalog, scope, capability contract, or plugin contribution."""


class ExpressionCollisionError(ExpressionConfigurationError):
    """Two different implementations were bound to the same name in one scope."""


class ExpressionsFrozenError(ExpressionConfigurationError):
    """An attempt to modify definitions after successful finalization."""


class ExpressionError(ExpressionsError):
    """Evaluation error with enough information for a template editor to report it.

    ``expression_id`` identifies the implementation; ``alias`` identifies what
    the user wrote. They are deliberately separate. ``span`` is the source range
    of the enclosing top-level call, when the error came from ``format_text``.
    Original Python exceptions are retained through exception chaining.
    """

    def __init__(
        self,
        message: str,
        *,
        expression_id: str | None = None,
        alias: str | None = None,
        scope_id: str | None = None,
        span: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.expression_id = expression_id
        self.alias = alias
        self.scope_id = scope_id
        self.span = span


class ExpressionNotFoundError(ExpressionError):
    """A template name is not bound in its selected scope."""


class ExpressionContextError(ExpressionError):
    """An evaluation does not satisfy its declared capability contracts."""


class ExpressionArgumentError(ExpressionError):
    """Template arguments do not match an expression's public parameters."""


class ExpressionExecutionError(ExpressionError):
    """An implementation or its renderer raised an unexpected exception."""
