from __future__ import annotations


__all__ = [
    'ResourceLoader',
    'Localization',
    'FluentTranslator',
]

from importlib.resources.abc import Traversable
from typing import Any, cast
from pathlib import Path
from collections.abc import Generator

from fluent.syntax import FluentParser
from fluent.runtime import FluentLocalization, AbstractResourceLoader
from fluent.syntax.ast import Resource

from .base import Translator, TranslationSource
from .types import TranslationResult


class ResourceLoader(AbstractResourceLoader):
    def __init__(self, source: TranslationSource) -> None:
        if isinstance(source, str):
            source = Path(source)
        self.source = source

    def resources(
        self, locale: str, resource_ids: list[str]
    ) -> Generator[list[Resource], None, None]:
        yield self._get_resources(self.source / locale)

    def _get_resources(self, path: Path | Traversable) -> list[Resource]:
        if not path.is_dir():
            return []

        resources = []
        for i in path.iterdir():
            if i.is_dir() and not i.name.startswith(('.', '_')):
                resources.extend(self._get_resources(i))
                continue
            if not i.is_file() or not i.name.endswith('.ftl') or i.name.startswith(('.', '_')):
                continue
            resources.append(FluentParser().parse(i.read_text(encoding='utf-8')))
        return resources

class Localization(FluentLocalization):
    def format_value(self, msg_id: str, args: dict[str, Any] | None = None) -> str:
        for bundle in self._bundles():
            if not bundle.has_message(msg_id):
                continue
            msg = bundle.get_message(msg_id)
            if not msg.value:
                continue
            val, _errors = bundle.format_pattern(msg.value, args)
            return cast(str, val)  # Never FluentNone when format_pattern called externally
        raise KeyError(f'Unable to find key {msg_id!r}.')


class FluentTranslator(Translator):
    def __init__(self, current_lang: str = 'ru_RU') -> None:
        super().__init__(current_lang=current_lang)
        self._localizations: dict[str, list[Localization]] = {}
        self._sources: list[TranslationSource] = []

    def add_translations(self, source: TranslationSource) -> None:
        if isinstance(source, str):
            source = Path(source)

        if source in self._sources:
            return

        self._sources.append(source)
        for lang, localizations in self._localizations.items():
            localizations.append(self._localization_from_source(source, lang))

    def translate_string(
        self,
        string: str,
        variables: dict[str, Any] | None = None,
        *,
        lang: str | None = None,
    ) -> TranslationResult:
        selected_lang = self._current_lang if lang is None else lang
        for i in reversed(self._localizations_for(selected_lang)):
            try:
                return TranslationResult(i.format_value(string, variables), translated=True)
            except KeyError:
                continue
        return TranslationResult(string, translated=False)

    def _localizations_for(self, lang: str) -> list[Localization]:
        if lang not in self._localizations:
            self._localizations[lang] = [
                self._localization_from_source(source, lang) for source in self._sources
            ]
        return self._localizations[lang]

    def _localization_from_source(self, source_path: TranslationSource, lang: str) -> Localization:
        return Localization(
            locales=[lang],
            resource_ids=[],
            resource_loader=ResourceLoader(source_path),
        )
