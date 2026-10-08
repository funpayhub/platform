"""Composition-based expressions: implementation IDs, scoped aliases, typed input.

Start with ``architecture.rst`` for the full design and ``examples.py`` for a
runnable marketplace/plugin integration. The new package reuses the existing
call syntax but never imports the old registry, context classes, or defaults.
It can be adopted independently without changing the current application.

The public API keeps three different identities separate:

* ``telegram_stars.amount``: a unique catalog implementation ID.
* ``stars_amount``: a template alias in a selected scope.
* ``hubplatform.order_reference``: a typed input-data capability contract.

All setup writes happen before ``ExpressionsManager.freeze``. Every evaluation
gets a fresh context and cache; repository services may be shared across calls.
"""

from __future__ import annotations

from hubplatform.expressions.syntax import Call

from .engine import FormattingResult, ExpressionsManager
from .errors import (
    ExpressionError,
    ExpressionsError,
    ExpressionContextError,
    ExpressionsFrozenError,
    ExpressionArgumentError,
    ExpressionNotFoundError,
    ExpressionCollisionError,
    ExpressionExecutionError,
    ExpressionConfigurationError,
)
from .scopes import Tagged, Provides, CompiledScope, ScopeSelector, BoundExpression
from .catalog import ExpressionCatalog, ExpressionDefinition
from .defaults import register_common
from .contracts import ORDER_REFERENCE, OrderReference
from .capabilities import Capability, EvaluationContext, ExpressionRuntime


__all__ = [
    'ORDER_REFERENCE',
    'BoundExpression',
    'Call',
    'Capability',
    'CompiledScope',
    'EvaluationContext',
    'ExpressionArgumentError',
    'ExpressionCatalog',
    'ExpressionCollisionError',
    'ExpressionConfigurationError',
    'ExpressionContextError',
    'ExpressionDefinition',
    'ExpressionError',
    'ExpressionExecutionError',
    'ExpressionNotFoundError',
    'ExpressionRuntime',
    'ExpressionsError',
    'ExpressionsFrozenError',
    'ExpressionsManager',
    'FormattingResult',
    'OrderReference',
    'Provides',
    'ScopeSelector',
    'Tagged',
    'register_common',
]
