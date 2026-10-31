from __future__ import annotations


__all__ = ['register_math_expressions']

import math
import random as random_module
from decimal import ROUND_HALF_UP, Decimal, localcontext
from collections.abc import Iterator

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ArgDocs, ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression
from hubplatform.expressions.call_context import ExpressionContext


type Number = int | float

CATEGORY = 'general.math'

DECIMAL_PRECISION = 100
ROUND_PRECISION = 400
MAX_ROUND_DIGITS = 20


_manager = ExpressionsManager({})


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


def _to_decimal(value: Number) -> Decimal:
    return Decimal(value) if isinstance(value, int) else Decimal(repr(value))


def _from_decimal(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise OverflowError('The result is too large.')
    return result


def _add(a: Number, b: Number) -> Number:
    if isinstance(a, int) and isinstance(b, int):
        return a + b
    with localcontext() as decimal_context:
        decimal_context.prec = DECIMAL_PRECISION
        return _from_decimal(_to_decimal(a) + _to_decimal(b))


def _sub(a: Number, b: Number) -> Number:
    if isinstance(a, int) and isinstance(b, int):
        return a - b
    with localcontext() as decimal_context:
        decimal_context.prec = DECIMAL_PRECISION
        return _from_decimal(_to_decimal(a) - _to_decimal(b))


def _mul(a: Number, b: Number) -> Number:
    if isinstance(a, int) and isinstance(b, int):
        return a * b
    with localcontext() as decimal_context:
        decimal_context.prec = DECIMAL_PRECISION
        return _from_decimal(_to_decimal(a) * _to_decimal(b))


def _div(a: Number, b: Number) -> Number:
    if b == 0:
        raise ZeroDivisionError('Division by zero.')

    if isinstance(a, int) and isinstance(b, int):
        quotient, remainder = divmod(a, b)
        if not remainder:
            return quotient

    with localcontext() as decimal_context:
        decimal_context.prec = DECIMAL_PRECISION
        return _from_decimal(_to_decimal(a) / _to_decimal(b))


@_manager.register(context_type=ExpressionContext, call_key='random', category=CATEGORY)
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


@_manager.register(context_type=ExpressionContext, call_key='sum', category=CATEGORY)
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
    result: Number = 0
    for number in _flatten_numbers(args):
        result = _add(result, number)
    return result


@_manager.register(context_type=ExpressionContext, call_key='min', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.min:description',
            'Наименьшее из переданных чисел. Вложенные списки тоже учитываются. '
            'Нужно передать хотя бы одно число. Пример: $min(5, 2, 9)',
        ),
        args_doc={
            'args': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.min.args:name',
                    'Числа',
                ),
                key='args',
                overview=I18nString(
                    'hubplatform.expressions.general:math.min.args:description',
                    'Числа, среди которых ищется наименьшее.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.min.args:possible_values',
                    'Любое число, целое или дробное',
                ),
                kind='positional_only',
            ),
        },
    )
)
async def min_number(ctx: ExpressionContext, *args: object) -> Number:
    numbers = list(_flatten_numbers(args))
    if not numbers:
        raise ValueError('At least one number is required.')
    return min(numbers)


@_manager.register(context_type=ExpressionContext, call_key='max', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.max:description',
            'Наибольшее из переданных чисел. Вложенные списки тоже учитываются. '
            'Нужно передать хотя бы одно число. Пример: $max(5, 2, 9)',
        ),
        args_doc={
            'args': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.max.args:name',
                    'Числа',
                ),
                key='args',
                overview=I18nString(
                    'hubplatform.expressions.general:math.max.args:description',
                    'Числа, среди которых ищется наибольшее.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.max.args:possible_values',
                    'Любое число, целое или дробное',
                ),
                kind='positional_only',
            ),
        },
    )
)
async def max_number(ctx: ExpressionContext, *args: object) -> Number:
    numbers = list(_flatten_numbers(args))
    if not numbers:
        raise ValueError('At least one number is required.')
    return max(numbers)


@_manager.register(context_type=ExpressionContext, call_key='round', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.round:description',
            'Округляет число до заданного количества знаков после запятой. '
            'Половинки округляются от нуля: 2.5 становится 3, а -2.5 становится -3. '
            'Без второго аргумента округляет до целого. Пример: $round(3.14159, 2)',
        ),
        args_doc={
            'number': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.round.number:name',
                    'Число',
                ),
                key='number',
                overview=I18nString(
                    'hubplatform.expressions.general:math.round.number:description',
                    'Число, которое нужно округлить.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.round.number:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
            'digits': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.round.digits:name',
                    'Знаков после запятой',
                ),
                key='digits',
                overview=I18nString(
                    'hubplatform.expressions.general:math.round.digits:description',
                    'Сколько знаков после запятой оставить. Отрицательное значение '
                    'округляет до десятков, сотен и т.д.',
                ),
                default='0',
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.round.digits:possible_values',
                    'Целое число от -20 до 20',
                ),
            ),
        },
    )
)
async def round_number(ctx: ExpressionContext, number: Number, digits: int = 0) -> Number:
    number = _require_number(number, 'number')
    if isinstance(digits, bool) or not isinstance(digits, int):
        raise TypeError(f'digits must be an integer, not {type(digits).__name__}.')
    if not -MAX_ROUND_DIGITS <= digits <= MAX_ROUND_DIGITS:
        raise ValueError(f'digits must be between -{MAX_ROUND_DIGITS} and {MAX_ROUND_DIGITS}.')

    if isinstance(number, int) and digits >= 0:
        return number

    with localcontext() as decimal_context:
        decimal_context.prec = ROUND_PRECISION
        rounded = _to_decimal(number).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)

    if digits > 0:
        return _from_decimal(rounded)
    return int(rounded)


@_manager.register(context_type=ExpressionContext, call_key='sub', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.sub:description',
            'Разность двух чисел: a - b. Пример: $sub(10, 3)',
        ),
        args_doc={
            'a': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.sub.a:name',
                    'Уменьшаемое',
                ),
                key='a',
                overview=I18nString(
                    'hubplatform.expressions.general:math.sub.a:description',
                    'Число, из которого вычитают.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.sub.a:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
            'b': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.sub.b:name',
                    'Вычитаемое',
                ),
                key='b',
                overview=I18nString(
                    'hubplatform.expressions.general:math.sub.b:description',
                    'Число, которое вычитают.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.sub.b:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
        },
    )
)
async def sub(ctx: ExpressionContext, a: Number, b: Number) -> Number:
    return _sub(_require_number(a, 'a'), _require_number(b, 'b'))


@_manager.register(context_type=ExpressionContext, call_key='mul', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.mul:description',
            'Произведение всех переданных чисел. Вложенные списки тоже перемножаются. '
            'Без аргументов результат равен 1. Пример: $mul(2, 3.5)',
        ),
        args_doc={
            'args': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.mul.args:name',
                    'Числа',
                ),
                key='args',
                overview=I18nString(
                    'hubplatform.expressions.general:math.mul.args:description',
                    'Любое количество чисел для умножения.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.mul.args:possible_values',
                    'Любое число, целое или дробное',
                ),
                kind='positional_only',
            ),
        },
    )
)
async def mul(ctx: ExpressionContext, *args: object) -> Number:
    result: Number = 1
    for number in _flatten_numbers(args):
        result = _mul(result, number)
    return result


@_manager.register(context_type=ExpressionContext, call_key='div', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.div:description',
            'Делит a на b. Если оба числа целые и делятся нацело, результат целый, '
            'иначе дробный. Деление на ноль приводит к ошибке. Пример: $div(10, 4)',
        ),
        args_doc={
            'a': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.div.a:name',
                    'Делимое',
                ),
                key='a',
                overview=I18nString(
                    'hubplatform.expressions.general:math.div.a:description',
                    'Число, которое делят.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.div.a:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
            'b': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.div.b:name',
                    'Делитель',
                ),
                key='b',
                overview=I18nString(
                    'hubplatform.expressions.general:math.div.b:description',
                    'Число, на которое делят.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.div.b:possible_values',
                    'Любое число, кроме нуля',
                ),
            ),
        },
    )
)
async def div(ctx: ExpressionContext, a: Number, b: Number) -> Number:
    return _div(_require_number(a, 'a'), _require_number(b, 'b'))


@_manager.register(context_type=ExpressionContext, call_key='percent', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        overview=I18nString(
            'hubplatform.expressions.general:math.percent:description',
            'Вычисляет процент от числа: value * percent / 100. '
            'Пример: $percent(200, 15) вернёт 30, то есть 15% от 200.',
        ),
        args_doc={
            'value': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.percent.value:name',
                    'Число',
                ),
                key='value',
                overview=I18nString(
                    'hubplatform.expressions.general:math.percent.value:description',
                    'Число, от которого считается процент.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.percent.value:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
            'percent': ArgDocs(
                name=I18nString(
                    'hubplatform.expressions.general:math.percent.percent:name',
                    'Процент',
                ),
                key='percent',
                overview=I18nString(
                    'hubplatform.expressions.general:math.percent.percent:description',
                    'Сколько процентов нужно взять.',
                ),
                possible_values=I18nString(
                    'hubplatform.expressions.general:math.percent.percent:possible_values',
                    'Любое число, целое или дробное',
                ),
            ),
        },
    )
)
async def percent(ctx: ExpressionContext, value: Number, percent: Number) -> Number:
    return _div(_mul(_require_number(value, 'value'), _require_number(percent, 'percent')), 100)


def register_math_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
