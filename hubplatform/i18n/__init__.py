from __future__ import annotations


__all__ = ['Translator', 'FluentTranslator', 'global_translator']

from functools import cache
from importlib.resources import files, as_file

from .base import Translator
from .fluent import FluentTranslator


@cache
def global_translator() -> Translator:
    translator = FluentTranslator()
    translator.add_translations(files(__package__).joinpath('locales'))
    return translator
