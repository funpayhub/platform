from __future__ import annotations

from hubplatform.exceptions import HubPlatformError


class ExpressionError(HubPlatformError): ...


class ExpressionExecutionError(ExpressionError):
    def __init__(self, expression_id: str, message: str | None = None) -> None:
        if message is None:
            message = f'An unexpected error occurred while executing expression {expression_id!r}.'
        self.expression_id = expression_id
        super().__init__(message)
