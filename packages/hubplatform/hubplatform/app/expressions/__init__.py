from __future__ import annotations


__all__ = [
    'GeneralActionContext',
    'GeneralMessageContext',
    'GeneralOrderContext',
    'GeneralReviewContext',
    'create_default_expressions_manager',
]

from typing import Any
from collections.abc import Mapping

from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.call_context import ExpressionContext

from .contexts import (
    GeneralOrderContext,
    GeneralActionContext,
    GeneralReviewContext,
    GeneralMessageContext,
)
from .math_expressions import register_math_expressions
from .text_expressions import register_text_expressions
from .user_expressions import register_user_expressions
from .order_expressions import register_order_expressions
from .review_expressions import register_review_expressions
from .general_expressions import register_general_expressions
from .message_expressions import register_message_expressions


def create_default_expressions_manager(
    context: Mapping[str, Any] | None = None,
) -> ExpressionsManager:
    manager = ExpressionsManager({} if context is None else context)
    manager.add_context(ExpressionContext, 'root')
    register_general_expressions(manager)
    register_math_expressions(manager)
    register_text_expressions(manager)
    register_user_expressions(manager)
    register_order_expressions(manager)
    register_review_expressions(manager)
    register_message_expressions(manager)
    return manager
