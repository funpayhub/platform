from __future__ import annotations


__all__ = [
    'time_expression',
    'random_expression',
]

import random
from typing import Any
from math import ceil, floor
from datetime import datetime

from .registry import ArgDocs, ExpressionDoc, ExpressionsRegistry
from .call_context import ExpressionCallContext


_time_formats = {
    'time': '%H:%M',
    'fulltime': '%H:%M:%S',
    'date': '%d.%m',
    'fulldate': '%d.%m.%Y',
    'dt': '%d.%m %H:%M',
    'fulldt': '%d.%m.%Y %H:%M:%S',
}


registry = ExpressionsRegistry()
registry.add_category(
    id='hubplatform:common',
    name='Common',
    description='Common expressions, that can be used without any context.',
    include_expressions=(),
    include_categories=(),
    supported_contexts=(ExpressionCallContext,),
)


@registry.add_expression(
    id='hubplatform:time',
    name='Date & Time',
    description=ExpressionDoc(
        overview='Date & Time',
        args_doc={
            'mode': ArgDocs(
                name='Режим',
                key='mode',
                overview='Режим форматирования даты и времени',
                default='time',
                possible_values={
                    'time': 'Время в формате ЧЧ:ММ',
                    'fulltime': 'Время в формате ЧЧ:ММ:СС',
                    'date': 'Дата в формате ДД.ММ',
                    'fulldate': 'Дата в формате ДД.ММ.ГГГГ',
                    'dt': 'Дата и время в формате ДД.ММ ЧЧ:ММ',
                    'fulldt': 'Дата и время в формате ДД.ММ.ГГГГ ЧЧ:ММ:СС',
                    'Кастомный формат': 'Любой формат, поддерживающийся Python DateTime. '
                    'Подробнее: https://docs.python.org/3/library/'
                    'datetime.html#strftime-strptime-behavior',
                },
            )
        },
    ),
    supported_contexts=(ExpressionCallContext,),
)
def time_expression(mode: str = 'time') -> str:
    if mode in _time_formats:
        return datetime.now().strftime(_time_formats[mode])
    return datetime.now().strftime(mode)


def random_expression(*args: Any, amount: int = 1, sep: str = ' ') -> str:
    return sep.join(random.choice(args) for _ in range(amount))


def round_expression(val: float, mode: str = 'floor') -> float:
    if mode == 'floor':
        return floor(val)
    if mode == 'ceil':
        return ceil(val)
    return round(val)
