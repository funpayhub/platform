from __future__ import annotations


__all__ = [
    'Translator',
    'TranslationSource',
]

from typing import Any
from abc import ABCMeta, abstractmethod
from pathlib import Path
from string.templatelib import Template, Interpolation
from importlib.resources.abc import Traversable

from hubplatform.i18n.types import TranslatableMixin, TranslationResult


type TranslationSource = str | Path | Traversable


class Translator(metaclass=ABCMeta):
    def __init__(self, current_lang: str = 'en') -> None:
        self._current_lang = current_lang

    @abstractmethod
    def add_translations(self, source: TranslationSource) -> None: ...

    def translate(
        self,
        val: str | TranslatableMixin | Template,
        variables: dict[str, Any] | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        if isinstance(val, TranslatableMixin):
            return val.translate_(self, lang=lang)
        if isinstance(val, Template):
            return self.translate_template(val, lang=lang)
        return self.translate_string(val, variables, lang=lang)

    def translate_template(
        self,
        val: Template,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        result = []
        for i in val:
            if isinstance(i, TranslatableMixin):
                result.append(i.translate_(self, lang=lang))
            elif isinstance(i, Interpolation):
                result.append(
                    str(i.value)
                    if not isinstance(i.value, TranslatableMixin)
                    else i.value.translate_(self, lang=lang)
                )
            else:
                result.append(i)
        return TranslationResult(value=''.join(result), translated=True)

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
