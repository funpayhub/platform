from __future__ import annotations


__all__ = [
    'HubPlatformError',
    'I18nException',
]

from typing import Any

from hubplatform.i18n import I18nString, Translator, TranslationResult


class HubPlatformError(Exception): ...


class TranslatableException(HubPlatformError):  # noqa: N818  # todo: remove
    def __init__(self, message: str, **kwargs: Any) -> None:
        self.message = message
        self.kwargs = kwargs
        super().__init__(self.format_message())

    def format_message(self) -> str:
        return self.message.format(**self.kwargs)


class BadHashError(TranslatableException): ...


class I18nException(HubPlatformError):  # noqa: N818
    def __init__(self, message: I18nString) -> None:
        super().__init__(message)
        self.message = message

    def translate(
        self,
        translator: Translator | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        return self.message.translate_(translator=translator, lang=lang)

    def __str__(self) -> str:
        return self.message.translate_(translator=None)
