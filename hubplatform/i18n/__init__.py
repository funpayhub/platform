from __future__ import annotations


__all__ = [
    'Translator',
    'FluentTranslator',
    'global_translator',
    'I18nString',
    'I18nException',
    'safe_formatter',
]

from functools import cache
from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable

from .base import Translator
from .types import I18nString, I18nException, TranslationResult, safe_formatter
from .fluent import FluentTranslator


def _locale_sources(root: Traversable) -> Iterator[Traversable]:
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if child.name == 'locales':
            yield child
            continue
        if child.name.startswith(('.', '__')):
            continue
        yield from _locale_sources(child)


@cache
def global_translator() -> Translator:
    translator = FluentTranslator()
    for source in _locale_sources(files('hubplatform')):
        translator.add_translations(source)
    return translator
