from __future__ import annotations


__all__ = [
    'I18nString',
    'I18nMultiString',
    'TranslationResult',
    'safe_formatter',
    'TranslatableMixin',
    'i',
    'im',
]

from typing import TYPE_CHECKING, Any
from abc import ABC, abstractmethod
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


class TranslatableMixin(ABC):
    @abstractmethod
    def translate_(
        self,
        translator: Translator | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult: ...


class I18nString(str, TranslatableMixin):
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
        if translator is not None:
            kwargs = self.prepare_args(translator=translator, lang=lang)
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
            k: v.translate_(translator=translator, lang=lang)
            if isinstance(v, TranslatableMixin)
            else v
            for k, v in self.kwargs.items()
        }

    def __add__(self, other: str) -> I18nMultiString:
        return I18nMultiString(self, other)

    def __iadd__(self, other: str) -> I18nMultiString:
        return self + other

    def __radd__(self, other: str) -> I18nMultiString:
        return I18nMultiString(other, self)


class I18nMultiString(str, TranslatableMixin):
    __slots__ = ('args',)

    args: tuple[str, ...]
    separator: str

    def __new__(cls, *args: str, separator: str = '') -> I18nMultiString:
        if not all(isinstance(arg, str) for arg in args):
            raise TypeError('All parts of `I18nMultiString` must be strings.')
        if not isinstance(separator, str):
            raise TypeError('Separator must be a string.')

        result = str.__new__(cls, separator.join(args))
        result.args = args
        result.separator = separator
        return result

    def translate_(
        self,
        translator: Translator | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        result = [
            i.translate_(translator, lang=lang) if isinstance(i, TranslatableMixin) else i
            for i in self.args
        ]
        return TranslationResult(self.separator.join(result), translated=True)

    def __add__(self, other: str) -> I18nMultiString:
        return I18nMultiString(*self.args, other, separator=self.separator)

    def __iadd__(self, other: str) -> I18nMultiString:
        return self + other

    def __radd__(self, other: str) -> I18nMultiString:
        return I18nMultiString(other, *self.args, separator=self.separator)


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


i = I18nString
im = I18nMultiString
