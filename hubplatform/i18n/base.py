from __future__ import annotations


__all__ = [
    'Translator',
]

from typing import Any
from abc import ABCMeta, abstractmethod
from pathlib import Path


class Translator(metaclass=ABCMeta):
    def __init__(self, current_lang: str = 'en') -> None:
        self._current_lang = current_lang

    @abstractmethod
    def add_translations(self, path: Path | str) -> None: ...

    @abstractmethod
    def translate(self, text: str, **variables: str) -> str: ...

    @property
    def current_lang(self) -> str:
        return self._current_lang

    def change_language(self, new_lang: str) -> None:
        self._current_lang = new_lang
