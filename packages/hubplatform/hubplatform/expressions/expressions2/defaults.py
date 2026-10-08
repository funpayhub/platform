"""Examples of common expressions needing no marketplace/event capability."""

from __future__ import annotations

import random
from typing import Any

from .engine import ExpressionsManager
from .capabilities import EvaluationContext


def register_common(manager: ExpressionsManager, *, scope_id: str = 'common') -> None:
    """Install a small shared vocabulary with an empty input contract.

    Utilities receive the evaluation context for a uniform callback API, but
    declare no required capabilities. Consequently every marketplace scope can
    reuse them without inheriting a BaseContext Python class.
    """
    catalog = manager.catalog

    @catalog.expression('hubplatform.upper', name='Uppercase', category='common')
    def upper(ctx: EvaluationContext, value: Any) -> str:
        """Convert a value to text, then uppercase it."""
        return str(value).upper()

    @catalog.expression('hubplatform.lower', name='Lowercase', category='common')
    def lower(ctx: EvaluationContext, value: Any) -> str:
        """Convert a value to text, then lowercase it."""
        return str(value).lower()

    @catalog.expression('hubplatform.random', name='Random choice', category='common')
    def random_choice(
        ctx: EvaluationContext, *values: Any, amount: int = 1, sep: str = ' '
    ) -> str:
        """Pick values independently on each invocation; never implicitly memoize."""
        if not values:
            raise ValueError('random needs at least one value.')
        if not isinstance(amount, int) or amount < 0:
            raise ValueError('random amount must be a nonnegative integer.')
        return sep.join(str(random.choice(values)) for _ in range(amount))

    @catalog.expression('hubplatform.round', name='Round', category='common')
    def round_value(ctx: EvaluationContext, value: float, digits: int = 0) -> float:
        """Return a number so enclosing expressions can continue to use arithmetic."""
        return round(value, digits)

    manager.add_scope(
        scope_id,
        bindings={
            'upper': 'hubplatform.upper',
            'lower': 'hubplatform.lower',
            'random': 'hubplatform.random',
            'round': 'hubplatform.round',
        },
    )
