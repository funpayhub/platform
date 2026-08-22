from __future__ import annotations


__all__ = ['Translator', 'FluentTranslator', 'global_translator']

from .base import Translator
from .fluent import FluentTranslator
from importlib.resources import files, as_file
from functools import cache


@cache
def global_translator() -> Translator:
    translator = FluentTranslator()
    with as_file(files(__package__).joinpath("locales")) as path:
        translator.add_translations(path)
    return translator
