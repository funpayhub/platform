from __future__ import annotations

from pathlib import Path

import pytest

from hubplatform.i18n.fluent import FluentTranslator


def write_translations(
    source: Path,
    locale: str,
    translations: str,
    filename: str = 'messages.ftl',
) -> None:
    locale_dir = source / locale
    locale_dir.mkdir(parents=True, exist_ok=True)
    (locale_dir / filename).write_text(translations, encoding='utf-8')


@pytest.fixture(scope='function')
def translator() -> FluentTranslator:
    tr = FluentTranslator()
    tr.change_language('en_US')
    return tr


def test_translates_messages_and_substitutes_variables(
    tmp_path: Path, translator: FluentTranslator
) -> None:
    write_translations(
        tmp_path,
        'en_US',
        'hello = Hello!\nwelcome = Welcome, { $name }!\n',
    )
    translator.add_translations(tmp_path)

    assert translator.translate('hello') == 'Hello!'
    assert translator.translate('welcome', name='Alice') == 'Welcome, Alice!'


def test_returns_message_id_when_translation_is_missing(
    tmp_path: Path, translator: FluentTranslator
) -> None:
    write_translations(tmp_path, 'en_US', 'known-message = Known message\n')
    translator.add_translations(tmp_path)

    assert translator.translate('missing-message') == 'missing-message'


def test_loads_translations_from_all_visible_ftl_files(
    tmp_path: Path, translator: FluentTranslator
) -> None:
    write_translations(tmp_path, 'en_US', 'first-message = First\n', 'first.ftl')
    write_translations(tmp_path, 'en_US', 'second-message = Second\n', 'second.ftl')
    write_translations(tmp_path, 'en_US', 'hidden-message = Hidden\n', '.hidden.ftl')
    write_translations(tmp_path, 'en_US', 'text-message = Text\n', 'messages.txt')
    write_translations(tmp_path / 'en_US', 'nested', 'nested-message = Nested\n')

    translator.add_translations(tmp_path)

    assert translator.translate('first-message') == 'First'
    assert translator.translate('second-message') == 'Second'
    assert translator.translate('hidden-message') == 'hidden-message'
    assert translator.translate('text-message') == 'text-message'
    assert translator.translate('nested-message') == 'nested-message'


def test_combines_multiple_translation_sources(
    tmp_path: Path, translator: FluentTranslator
) -> None:
    first_source = tmp_path / 'first'
    second_source = tmp_path / 'second'
    write_translations(first_source, 'en_US', 'first-message = First\n')
    write_translations(second_source, 'en_US', 'second-message = Second\n')

    translator.add_translations(first_source)
    translator.add_translations(str(second_source))

    assert translator.translate('first-message') == 'First'
    assert translator.translate('second-message') == 'Second'


def test_change_language_reloads_added_sources(tmp_path: Path) -> None:
    write_translations(tmp_path, 'en_US', 'greeting = Hello, { $name }!\n')
    write_translations(tmp_path, 'ru_RU', 'greeting = Привет, { $name }!\n')
    translator = FluentTranslator()
    translator.add_translations(tmp_path)

    assert translator.translate('greeting', name='Alice') == 'Hello, Alice!'

    translator.change_language('ru_RU')

    assert translator.current_lang == 'ru_RU'
    assert translator.translate('greeting', name='Alice') == 'Привет, Алиса!'
