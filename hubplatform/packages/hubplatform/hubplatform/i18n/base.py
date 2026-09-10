from __future__ import annotations


__all__ = [
    'Translator',
    'TranslationSource',
]


from typing import Any
from abc import ABCMeta, abstractmethod
from pathlib import Path
from importlib.resources.abc import Traversable

from hubplatform.i18n.types import I18nString, TranslationResult


type TranslationSource = str | Path | Traversable


class Translator(metaclass=ABCMeta):
    def __init__(self, current_lang: str = 'en') -> None:
        self._current_lang = current_lang

    @abstractmethod
    def add_translations(self, source: TranslationSource) -> None: ...

    def translate(
        self,
        val: str | I18nString,
        variables: dict[str, Any] | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        if isinstance(val, I18nString):
            return val.translate_(self, lang=lang)
        return self.translate_string(val, variables, lang=lang)

    @abstractmethod
    def translate_string(
        self,
        string: str,
        variables: dict[str, Any] | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult: ...

    @property
    def current_lang(self) -> str:
        return self._current_lang

    def change_language(self, new_lang: str) -> None:
        self._current_lang = new_lang
