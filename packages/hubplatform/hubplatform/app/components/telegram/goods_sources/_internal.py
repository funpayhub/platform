from __future__ import annotations


__all__ = [
    'DEFAULT_FILE_SOURCES_DIRECTORY',
    'PRODUCT_PREVIEW_LIMIT',
    'clip_index_ranges',
    'file_source_path',
    'parse_goods',
    'parse_index_ranges',
    'remove_goods_by_ranges',
    'serialize_goods',
]

import re
from pathlib import Path
from collections.abc import Sequence

from hubplatform.goods_source import (
    GoodsSource,
)


PRODUCT_PREVIEW_LIMIT = 200
DEFAULT_FILE_SOURCES_DIRECTORY = Path('storage') / 'goods_sources'

IndexRange = tuple[int, int]


def _unescape_product(product: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(product):
        char = product[index]
        if char != '\\' or index + 1 >= len(product):
            result.append(char)
            index += 1
            continue

        escaped = product[index + 1]
        if escaped == 'n':
            result.append('\n')
            index += 2
        elif escaped == '\\':
            result.append('\\')
            index += 2
        else:
            result.extend(('\\', escaped))
            index += 2
    return ''.join(result)


def parse_goods(content: str) -> list[str]:
    """Parse one product per physical line, supporting ``\\n`` inside a product."""
    return [_unescape_product(line) for line in content.splitlines() if line.strip()]


def _escape_product(product: str) -> str:
    normalized = product.replace('\r\n', '\n').replace('\r', '\n')
    return normalized.replace('\\', '\\\\').replace('\n', '\\n')


def serialize_goods(goods: Sequence[str]) -> str:
    """Serialize products in the same lossless format accepted by :func:`parse_goods`."""
    return '\n'.join(_escape_product(product) for product in goods)


def parse_index_ranges(value: str) -> list[IndexRange]:
    """Parse 1-based indexes and ranges, then return merged 0-based ranges."""
    normalized = re.sub(r'\s*[-–—]\s*', '-', value.strip())
    tokens = [token for token in re.split(r'[\s,;]+', normalized) if token]
    if not tokens:
        raise ValueError('Укажите хотя бы один индекс.')

    ranges: list[IndexRange] = []
    for token in tokens:
        match = re.fullmatch(r'(\d+)(?:-(\d+))?', token)
        if match is None:
            raise ValueError(f'Некорректный индекс или диапазон: {token!r}.')

        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < 1:
            raise ValueError('Индексы должны быть больше нуля.')
        if first > last:
            raise ValueError(f'Начало диапазона не может быть больше конца: {token!r}.')
        ranges.append((first - 1, last - 1))

    merged: list[IndexRange] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def clip_index_ranges(ranges: Sequence[IndexRange], goods_amount: int) -> list[IndexRange]:
    if goods_amount < 0:
        raise ValueError('Количество товаров не может быть отрицательным.')
    if goods_amount == 0:
        return []

    last_index = goods_amount - 1
    return [(start, min(end, last_index)) for start, end in ranges if start <= last_index]


async def remove_goods_by_ranges(
    source: GoodsSource,
    ranges: Sequence[IndexRange],
) -> int:
    clipped = clip_index_ranges(ranges, await source.len())
    for start, end in reversed(clipped):
        await source.remove_goods(start, end - start + 1)
    return sum(end - start + 1 for start, end in clipped)


def file_source_path(name: str) -> Path:
    normalized = name.strip()
    if not normalized:
        raise ValueError('название не может быть пустым.')
    if len(normalized) > 128:
        raise ValueError('название не может быть длиннее 128 символов.')
    if normalized in {'.', '..'} or '/' in normalized or '\\' in normalized:
        raise ValueError('название не должно содержать путь.')
    if '\x00' in normalized:
        raise ValueError('название содержит недопустимый символ.')

    filename = normalized if Path(normalized).suffix else f'{normalized}.txt'
    return (DEFAULT_FILE_SOURCES_DIRECTORY / filename).resolve()
