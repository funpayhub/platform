from __future__ import annotations


__all__ = ['Translator', 'FluentTranslator', 'global_translator']

from .base import Translator
from .fluent import FluentTranslator


_global_translator: Translator | None = None


def global_translator() -> Translator:
    global _global_translator
    if _global_translator is None:
        _global_translator = FluentTranslator()
    return _global_translator
