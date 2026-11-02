from __future__ import annotations

from dataclasses import dataclass

from hubplatform.expressions.definition import ExpressionDefinition

from .category import CategoryPath


@dataclass(frozen=True)
class ExpressionEnvelope:
    expression: ExpressionDefinition
    call_key: str
    category: CategoryPath | None = None
