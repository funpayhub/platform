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

from .base import Translator


class ResourceLoader(AbstractResourceLoader):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def resources(
        self, locale: str, resource_ids: list[str]
    ) -> Generator[list[Resource], None, None]:
        path = self.path / locale
        if not path.exists() or not path.is_dir():
            yield []

        resources = []
        for i in path.iterdir():
            if not i.is_file() or i.suffix != '.ftl' or i.name.startswith('.'):
                continue

            with open(i, 'r', encoding='utf-8') as f:
                resources.append(FluentParser().parse(f.read()))
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
        self._sources: set[Path] = set()

    def add_translations(self, path: Path | str) -> None:
        path = Path(path)
        if path in self._sources:
            return

        self._sources.add(path)
        self._localizers.append(self._localizer_from_source(path))

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

    def _localizer_from_source(self, source_path: Path) -> Localization:
        return Localization(
            locales=[self._current_lang],
            resource_ids=[],
            resource_loader=ResourceLoader(source_path),
        )
