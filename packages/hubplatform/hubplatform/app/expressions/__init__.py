from __future__ import annotations


__all__ = ['create_default_expressions_manager']

from typing import Any
from collections.abc import Mapping

from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.call_context import ExpressionContext

from .math_expressions import register_math_expressions
from .text_expressions import register_text_expressions
from .general_expressions import register_general_expressions


def create_default_expressions_manager(
    context: Mapping[str, Any] | None = None,
) -> ExpressionsManager:
    manager = ExpressionsManager({} if context is None else context)
    manager.add_context(ExpressionContext, 'root')
    register_general_expressions(manager)
    register_math_expressions(manager)
    register_text_expressions(manager)
    return manager
