from __future__ import annotations

from typing import Any


class HubPlatformError(Exception):  # noqa: N818
    ...


class TranslatableException(HubPlatformError):  # noqa: N818
    def __init__(self, message: str, **kwargs: Any) -> None:
        self.message = message
        self.kwargs = kwargs
        super().__init__(self.format_message())

    def format_message(self) -> str:
        return self.message.format(**self.kwargs)


class BadHashError(TranslatableException): ...
