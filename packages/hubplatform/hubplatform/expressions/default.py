from __future__ import annotations


__all__ = [
    'time_expression',
    'random_expression',
]

import random
from typing import Any
from math import ceil, floor
from datetime import datetime


_time_formats = {
    'time': '%H:%M',
    'fulltime': '%H:%M:%S',
    'date': '%d.%m',
    'fulldate': '%d.%m.%Y',
    'dt': '%d.%m %H:%M',
    'fulldt': '%d.%m.%Y %H:%M:%S',
}


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
