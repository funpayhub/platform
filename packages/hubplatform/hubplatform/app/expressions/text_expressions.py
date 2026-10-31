from __future__ import annotations


__all__ = ['register_text_expressions']

from typing import Any
from collections.abc import Mapping

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ArgDocs, ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.call_context import ExpressionContext


CATEGORY = 'general.text'


_manager = ExpressionsManager({})


def _require_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise TypeError(f'text must be a string or a number, not {type(value).__name__}.')


@_manager.register(context_type=ExpressionContext, call_key='upper', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:text.upper:description',
            'Переводит текст в ВЕРХНИЙ РЕГИСТР. Пример: $upper(привет)',
        ),
        args_doc={
            'text': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:text.upper.text:name',
                    'Текст',
                ),
                key='text',
                overview=I18nString(
                    'hubplatform.expressions.general:text.upper.text:description',
                    'Текст, который нужно преобразовать.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:text.upper.text:possible_values',
                    'Любой текст или число',
                ),
            ),
        },
    )
)
async def upper(ctx: ExpressionContext, text: Any) -> str:
    return _require_text(text).upper()


@_manager.register(context_type=ExpressionContext, call_key='lower', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:text.lower:description',
            'Переводит текст в нижний регистр. Пример: $lower(ПРИВЕТ)',
        ),
        args_doc={
            'text': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:text.lower.text:name',
                    'Текст',
                ),
                key='text',
                overview=I18nString(
                    'hubplatform.expressions.general:text.lower.text:description',
                    'Текст, который нужно преобразовать.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:text.lower.text:possible_values',
                    'Любой текст или число',
                ),
            ),
        },
    )
)
async def lower(ctx: ExpressionContext, text: Any) -> str:
    return _require_text(text).lower()


@_manager.register(context_type=ExpressionContext, call_key='capitalize', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:text.capitalize:description',
            'Делает первую букву текста заглавной, остальные символы не меняет. '
            'Пример: $capitalize("привет, Вася")',
        ),
        args_doc={
            'text': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:text.capitalize.text:name',
                    'Текст',
                ),
                key='text',
                overview=I18nString(
                    'hubplatform.expressions.general:text.capitalize.text:description',
                    'Текст, который нужно преобразовать.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:text.capitalize.text:possible_values',
                    'Любой текст или число',
                ),
            ),
        },
    )
)
async def capitalize(ctx: ExpressionContext, text: Any) -> str:
    value = _require_text(text)
    return value[:1].upper() + value[1:]


@_manager.register(context_type=ExpressionContext, call_key='trim', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:text.trim:description',
            'Удаляет пробелы и переводы строк в начале и конце текста. '
            'Пример: $trim("  привет  ")',
        ),
        args_doc={
            'text': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:text.trim.text:name',
                    'Текст',
                ),
                key='text',
                overview=I18nString(
                    'hubplatform.expressions.general:text.trim.text:description',
                    'Текст, который нужно очистить.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:text.trim.text:possible_values',
                    'Любой текст или число',
                ),
            ),
        },
    )
)
async def trim(ctx: ExpressionContext, text: Any) -> str:
    return _require_text(text).strip()


@_manager.register(context_type=ExpressionContext, call_key='length', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:text.length:description',
            'Количество символов в тексте. Для списка возвращает количество элементов. '
            'Пример: $length(привет)',
        ),
        args_doc={
            'text': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:text.length.text:name',
                    'Текст',
                ),
                key='text',
                overview=I18nString(
                    'hubplatform.expressions.general:text.length.text:description',
                    'Текст, список или число.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:text.length.text:possible_values',
                    'Любой текст, число или список',
                ),
            ),
        },
    )
)
async def length(ctx: ExpressionContext, text: Any) -> int:
    if isinstance(text, (tuple, list, Mapping)):
        return len(text)
    return len(_require_text(text))


def register_text_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
