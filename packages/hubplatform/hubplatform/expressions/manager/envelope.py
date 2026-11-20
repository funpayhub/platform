from __future__ import annotations

from dataclasses import dataclass

from hubplatform.expressions.definition import ExpressionDefinition
from hubplatform.expressions.requirement import Requirement

from .category import CategoryPath


@dataclass(frozen=True)
class ExpressionEnvelope:
    expression: ExpressionDefinition
    call_key: str
    category: CategoryPath | None = None
    override: bool = False
    """``True`` if the expression replaces a less specific expression with the same call key."""

    @property
    def requirement(self) -> Requirement:
        return self.expression.requirement
