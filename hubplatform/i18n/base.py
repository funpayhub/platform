from __future__ import annotations


__all__ = [
    'Translator',
    'TranslationSource',
]


from typing import Any
from abc import ABCMeta, abstractmethod
from pathlib import Path
from importlib.resources.abc import Traversable


type TranslationSource = str | Path | Traversable


class Translator(metaclass=ABCMeta):
    def __init__(self, current_lang: str = 'en') -> None:
        self._current_lang = current_lang

    @abstractmethod
    def add_translations(self, source: TranslationSource) -> None: ...

    @abstractmethod
    def translate(self, text: str, **variables: Any) -> str: ...

    @property
    def current_lang(self) -> str:
        return self._current_lang

    def change_language(self, new_lang: str) -> None:
        self._current_lang = new_lang
