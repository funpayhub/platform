from __future__ import annotations


__all__ = [
    'ResourceLoader',
    'Localization',
    'FluentTranslator',
]

from typing import Any, cast
from pathlib import Path
from collections.abc import Generator

from fluent.syntax import FluentParser
from fluent.runtime import FluentLocalization, AbstractResourceLoader
from fluent.syntax.ast import Resource

from .base import Translator, TranslationSource


class ResourceLoader(AbstractResourceLoader):
    def __init__(self, source: TranslationSource) -> None:
        if isinstance(source, str):
            source = Path(source)
        self.source = source

    def resources(
        self, locale: str, resource_ids: list[str]
    ) -> Generator[list[Resource], None, None]:
        path = self.source / locale
        if not path.is_dir():
            yield []
            return

        resources = []
        for i in path.iterdir():
            if not i.is_file() or not i.name.endswith('.ftl') or i.name.startswith('.'):
                continue

            resources.append(FluentParser().parse(i.read_text(encoding='utf-8')))
        yield resources


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
        self._localizers: list[Localization] = []
        self._sources: set[TranslationSource] = set()

    def add_translations(self, source: TranslationSource) -> None:
        if isinstance(source, str):
            source = Path(source)

        if source in self._sources:
            return

        self._sources.add(source)
        self._localizers.append(self._localizer_from_source(source))

    def translate(self, text: str, **variables: str) -> str:
        for i in self._localizers:
            try:
                return i.format_value(text, variables)
            except KeyError:
                continue
        return text

    def change_language(self, new_lang: str) -> None:
        super().change_language(new_lang)
        self._localizers = [self._localizer_from_source(i) for i in self._sources]

    def _localizer_from_source(self, source_path: TranslationSource) -> Localization:
        return Localization(
            locales=[self._current_lang],
            resource_ids=[],
            resource_loader=ResourceLoader(source_path),
        )
