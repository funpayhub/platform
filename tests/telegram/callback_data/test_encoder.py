from __future__ import annotations

import logging
from typing import Any
from itertools import chain

import pytest

from hubplatform.telegram.callback_data._compact_format import dump_compact, loads_compact


logger = logging.getLogger('tests')

_ATOMS = [
    123,
    123.321,
    -123,
    -123.321,
    True,
    False,
    None,
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


def _IN_LIST():
    yield from ((i,) for i in _ATOMS)
    yield from ((i, j) for i in _ATOMS for j in _ATOMS)


def _INNER_LIST():
    yield from ((i,) for i in _IN_LIST())
    yield from ((i, j) for i in _ATOMS for j in _IN_LIST())


def _ok(k):
    if isinstance(k, bool):
        return False
    try:
        hash(k)
        return True
    except Exception:
        return False


def _IN_DICT():
    yield from ({k: v} for k in _ATOMS if _ok(k) for v in _ATOMS)


def normalize_value(val: Any) -> Any:
    if isinstance(val, bool):
        return int(val)

    if isinstance(val, list | tuple):
        return [normalize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: normalize_value(v) for k, v in val.items()}

    return val


@pytest.mark.parametrize('val', _ATOMS)
def test_atom_persistence(val):
    encoded = dump_compact(val)
    assert val == loads_compact(encoded)


@pytest.mark.parametrize('val', chain(_IN_LIST(), _INNER_LIST()))
def test_list_persistence(val):
    encoded = dump_compact(val)
    normalized_value = normalize_value(val)
    logger.info('Input: %s | Normalized: %s | Encoded: %s', val, normalized_value, encoded)
    assert normalized_value == loads_compact(encoded)


@pytest.mark.parametrize('val', _IN_DICT())
def test_dict_persistence(val):
    encoded = dump_compact(val)
    normalized_value = normalize_value(val)
    logger.info('Input: %s | Normalized: %s | Encoded: %s', val, normalized_value, encoded)
    assert normalized_value == loads_compact(encoded)
