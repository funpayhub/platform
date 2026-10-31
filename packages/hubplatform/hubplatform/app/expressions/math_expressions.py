from __future__ import annotations


__all__ = ['register_math_expressions']

import math
import random as random_module
from collections.abc import Iterator

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ArgDocs, ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.call_context import ExpressionContext


type Number = int | float

CATEGORY = 'general.math'


def _require_number(value: object, name: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f'{name} must be a number, not {type(value).__name__}.')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number.')
    return value


def _flatten_numbers(values: tuple[object, ...] | list[object]) -> Iterator[Number]:
    for value in values:
        if isinstance(value, (tuple, list)):
            yield from _flatten_numbers(value)
        else:
            yield _require_number(value, 'Every argument')


@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.random:description',
            'Случайное число от min до max, обе границы включены. Если оба числа целые, '
            'результат целый, иначе дробный. Порядок min и max не важен. '
            'Пример: $random(1, 100)',
        ),
        args_doc={
            'min': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.random.min:name',
                    'Нижняя граница',
                ),
                key='min',
                overview=I18nString(
                    'hubplatform.expressions.general:math.random.min:description',
                    'Один из концов диапазона.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.random.min:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
            'max': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.random.max:name',
                    'Верхняя граница',
                ),
                key='max',
                overview=I18nString(
                    'hubplatform.expressions.general:math.random.max:description',
                    'Другой конец диапазона.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.random.max:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
        },
    )
)
async def random(ctx: ExpressionContext, min: Number, max: Number) -> Number:
    min, max = _require_number(min, 'min'), _require_number(max, 'max')
    if min > max:
        min, max = max, min

    if isinstance(min, int) and isinstance(max, int):
        return random_module.randint(min, max)
    return random_module.uniform(min, max)


@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.sum:description',
            'Сумма всех переданных чисел. Вложенные списки тоже суммируются. '
            'Без аргументов результат равен 0. Пример: $sum(1, 2.5, 3)',
        ),
        args_doc={
            'args': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.sum.args:name',
                    'Числа',
                ),
                key='args',
                overview=I18nString(
                    'hubplatform.expressions.general:math.sum.args:description',
                    'Любое количество чисел для сложения.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.sum.args:possible_values',
                    'Любое число, целое или дробное',
                ),
                kind='positional_only',
            ),
        },
    )
)
async def sum_numbers(ctx: ExpressionContext, *args: object) -> Number:
    numbers = list(_flatten_numbers(args))
    if any(isinstance(i, float) for i in numbers):
        return math.fsum(numbers)
    return sum(numbers)


def register_math_expressions(manager: ExpressionsManager) -> None:
    manager.add_expression(random, ExpressionContext, 'random', category=CATEGORY)
    manager.add_expression(sum_numbers, ExpressionContext, 'sum', category=CATEGORY)
