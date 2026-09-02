from __future__ import annotations


__all__ = ['I18nString', 'TranslationResult', 'safe_formatter']

from typing import TYPE_CHECKING, Any
from string import Formatter
from collections.abc import Mapping, Sequence


if TYPE_CHECKING:
    from .base import Translator


class SafeFormatter(Formatter):
    def get_value(self, key: str | int, args: Sequence[Any], kwargs: Mapping[str, Any]) -> Any:
        missing = f'{{{key}}}'
        if isinstance(key, int):
            return args[key] if len(args) >= key + 1 else missing
        return kwargs.get(key, missing)


safe_formatter = SafeFormatter()


class I18nString(str):
    __slots__ = ('key', 'fallback', 'kwargs')

    key: str
    fallback: str
    kwargs: dict[str, Any]

    def __new__(
        cls,
        key: str,
        fallback: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> I18nString:
        if fallback is None:
            fallback = key
        if kwargs is None:
            kwargs = {}

        result = str.__new__(cls, safe_formatter.format(fallback, **kwargs))
        result.key = key
        result.fallback = fallback
        result.kwargs = kwargs
        return result

    def translate_(
        self,
        translator: Translator | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        kwargs = self.prepare_args(translator=translator, lang=lang)
        if translator is not None:
            result = translator.translate_string(self.key, kwargs, lang=lang)
            if result.translated:
                return result

        return TranslationResult(self.fallback, translated=False)

    def prepare_args(
        self,
        translator: Translator | None = None,
        *,
        lang: str | None = None,
    ) -> dict[str, Any]:
        if not self.kwargs:
            return {}

        return {
            k: v.translate_(translator=translator, lang=lang) if isinstance(v, I18nString) else v
            for k, v in self.kwargs.items()
        }


class TranslationResult(str):
    __slots__ = ('translated',)
    translated: bool

    def __new__(
        cls,
        value: str,
        *,
        translated: bool,
    ) -> TranslationResult:
        result = str.__new__(cls, value)
        result.translated = translated
        return result
