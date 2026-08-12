from __future__ import annotations

import logging
from typing import Any
from itertools import chain
from collections.abc import Generator

import pytest

from hubplatform.telegram.callback_data.compact_encoder import dumps_compact, loads_compact


logger = logging.getLogger('tests')

_ATOMS = [
    123,
    123.321,
    -123,
    -123.321,
    True,
    False,
    None,
    'new\nline',
    '123',
    'some_string',
    '~',
    '^',
    '[',
    ']',
    '[]',
    '{',
    '}',
    '{}',
    '[ab',
    'a[b',
    'ab[',
    ']ab',
    'a]b',
    'ab]',
    '[a]b',
    'a[b]',
    '[ab]',
    '[a[b]',
    'a]b]',
    '{ab',
    'ab}',
    '{ab}',
    '{a:b}',
    'a{b',
    'a}b',
    ':ab',
    'a:b',
    'ab:',
    ':',
    ',ab',
    'a,b',
    'ab,',
    ',',
    (),
]


def in_seq() -> Generator[Any, None, None]:
    yield from ((i,) for i in _ATOMS)
    yield from ((i, j) for i in _ATOMS for j in _ATOMS)


def seq_in_seq() -> Generator[Any, None, None]:
    yield from ((i,) for i in in_seq())
    yield from ((i, j) for i in _ATOMS for j in in_seq())


def _ok(k: Any) -> bool:
    if isinstance(k, bool):
        return False
    try:
        hash(k)
        return True
    except Exception:
        return False


def in_mapping() -> Generator[Any, None, None]:
    yield from ({k: v} for k in _ATOMS if _ok(k) for v in chain(_ATOMS, in_seq()))


def normalize_value(val: Any) -> Any:
    if isinstance(val, bool):
        return int(val)

    if isinstance(val, list | tuple):
        return [normalize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: normalize_value(v) for k, v in val.items()}

    return val


@pytest.mark.parametrize('val', _ATOMS)
def test_atom_persistence(val: Any) -> None:
    encoded = dumps_compact(val)
    normalized_value = normalize_value(val)
    assert normalized_value == loads_compact(encoded)


@pytest.mark.slow
@pytest.mark.parametrize('val', list(chain(in_seq(), seq_in_seq())))
def test_list_persistence(val: Any) -> None:
    encoded = dumps_compact(val)
    normalized_value = normalize_value(val)
    logger.info('Input: %s | Normalized: %s | Encoded: %s', val, normalized_value, encoded)
    assert normalized_value == loads_compact(encoded)


@pytest.mark.slow
@pytest.mark.parametrize('val', list(in_mapping()))
def test_dict_persistence(val: Any) -> None:
    encoded = dumps_compact(val)
    normalized_value = normalize_value(val)
    logger.info('Input: %s | Normalized: %s | Encoded: %s', val, normalized_value, encoded)
    assert normalized_value == loads_compact(encoded)
