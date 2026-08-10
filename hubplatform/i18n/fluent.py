from __future__ import annotations

from typing import Any
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
            if not i.is_file():
                continue

            if i.suffix != '.ftl':
                continue

            if i.name.startswith('.'):
                continue

            with open(i, 'r', encoding='utf-8') as f:
                resources.append(FluentParser().parse(f.read()))

        yield resources


class FluentTranslator(Translator):
    def __init__(self, current_lang: str = 'en_US') -> None:
        super().__init__(current_lang=current_lang)
        self._localizers: list[FluentLocalization] = []
        self._sources: set[Path] = set()

    def add_translations(self, path: Path | str) -> None:
        path = Path(path)
        if path in self._sources:
            return

        self._sources.add(path)
        self._localizers.append(self._localizer_from_source(path))

    def translate(self, text: str, variables: dict[str, Any] | None = None) -> str:
        for i in self._localizers:
            r = i.format_value(text, variables)
            if r != text:
                return r
        return text

    def change_language(self, new_lang: str) -> None:
        super().change_language(new_lang)
        self._localizers = [self._localizer_from_source(i) for i in self._sources]

    def _localizer_from_source(self, source_path: Path) -> FluentLocalization:
        return FluentLocalization(
            locales=[self._current_lang],
            resource_ids=[],
            resource_loader=ResourceLoader(source_path),
        )
