from __future__ import annotations


__all__ = ['register_general_expressions']

import random as random_module
from typing import Any
from datetime import datetime
from collections.abc import Mapping

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ArgDocs, ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.call_context import ExpressionContext


CATEGORY = 'general'

TIME_MODES: Mapping[str, str] = {
    'date': '%d.%m',
    'fulldate': '%d.%m.%Y',
    'time': '%H:%M',
    'fulltime': '%H:%M:%S',
    'datetime': '%d.%m %H:%M',
    'fulldatetime': '%d.%m.%Y %H:%M:%S',
}


_manager = ExpressionsManager({})


@_manager.register(context_type=ExpressionContext, call_key='time', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general.time:description',
            'Текущие дата и время в российском формате (день.месяц.год, 24-часовой формат). '
            'Пример: $time(fulldate)',
        ),
        args_doc={
            'mode': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general.time.mode:name',
                    'Формат',
                ),
                key='mode',
                overview=I18nString(
                    'hubplatform.expressions.general.time.mode:description',
                    'Один из готовых режимов или собственный шаблон Python strftime, '
                    'например %d.%m.%Y %H:%M. Шаблон должен содержать "%".',
                ),
                possible_values={
                    'date': I18nString(
                        'hubplatform.expressions.general.time.mode.date:description',
                        'Дата без года: ДД.ММ',
                    ),
                    'fulldate': I18nString(
                        'hubplatform.expressions.general.time.mode.fulldate:description',
                        'Дата с годом: ДД.ММ.ГГГГ',
                    ),
                    'time': I18nString(
                        'hubplatform.expressions.general.time.mode.time:description',
                        'Время без секунд: ЧЧ:ММ',
                    ),
                    'fulltime': I18nString(
                        'hubplatform.expressions.general.time.mode.fulltime:description',
                        'Время с секундами: ЧЧ:ММ:СС',
                    ),
                    'datetime': I18nString(
                        'hubplatform.expressions.general.time.mode.datetime:description',
                        'Дата без года и время без секунд: ДД.ММ ЧЧ:ММ',
                    ),
                    'fulldatetime': I18nString(
                        'hubplatform.expressions.general.time.mode.fulldatetime:description',
                        'Дата с годом и время с секундами: ДД.ММ.ГГГГ ЧЧ:ММ:СС',
                    ),
                },
            ),
        },
    )
)
async def time(ctx: ExpressionContext, mode: str) -> str:
    if not isinstance(mode, str):
        raise TypeError(f'mode must be a string, not {type(mode).__name__}.')

    template = TIME_MODES.get(mode.strip())
    if template is None:
        if '%' not in mode:
            raise ValueError(
                f'Unknown time mode {mode!r}. Use one of {", ".join(TIME_MODES)} '
                f'or a strftime template that contains "%".'
            )
        template = mode
    return datetime.now().strftime(template)


@_manager.register(context_type=ExpressionContext, call_key='choice', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general.choice:description',
            'Случайно выбирает один из переданных вариантов. Все варианты равновероятны. '
            'Нужно передать хотя бы один вариант. '
            'Пример: $choice(Привет, Здравствуйте, Добрый день)',
        ),
        args_doc={
            'variants': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general.choice.variants:name',
                    'Варианты',
                ),
                key='variants',
                overview=I18nString(
                    'hubplatform.expressions.general.choice.variants:description',
                    'Значения, из которых выбирается одно.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general.choice.variants:possible_values',
                    'Любой текст, число или результат другого выражения',
                ),
                kind='positional_only',
            ),
        },
    )
)
async def choice(ctx: ExpressionContext, *variants: Any) -> Any:
    if not variants:
        raise ValueError('At least one variant is required.')
    return random_module.choice(variants)


def register_general_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
