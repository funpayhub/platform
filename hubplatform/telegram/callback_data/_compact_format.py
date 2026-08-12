from __future__ import annotations

import json
from typing import Any


_OPEN_SPECIAL = frozenset('[{')
_SPECIAL = frozenset('}]:"')


def _can_dump_string_without_quotes(value: str) -> bool:
    if not value:
        return False

    if value[0] in _OPEN_SPECIAL:
        return False

    if any(char in value for char in _SPECIAL):
        return False

    if value == '^':
        return False

    try:
        json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return True
    else:
        return False


def dump_compact(value: Any, *, root: bool = True, none_edge: bool = False) -> str:
    if isinstance(value, bool):
        return '1' if value else '0'
    if value is None:
        return ''
    if type(value) in (int, float):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    if isinstance(value, str):
        if not value:
            return '^'
        if value == '~' and none_edge:
            return '"~"'
        if _can_dump_string_without_quotes(value):
            return json.dumps(value, ensure_ascii=False)[1:-1]
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, tuple | list):
        if len(value) == 1 and value[0] is None:
            value_str = '~'
        elif len(value) == 1 and value[0] == '~':
            value_str = dump_compact(value[0], none_edge=True)
        else:
            value_str = ':'.join([dump_compact(i, root=False) for i in value])

        return f':{value_str}' if root else f'[{value_str}]'

    if isinstance(value, dict):
        if not value:
            return '{}'

        if len(value) == 1 and None in value:
            if value[None] is None:
                return '{~}'
            return '{:' + dump_compact(value[None], root=False) + '}'

        pairs = []
        for key, value in value.items():
            if key is None:
                key_str = '~'
            elif isinstance(key, dict):
                raise ValueError('Dict key cannot be another dict.')
            elif isinstance(key, bool):
                raise ValueError('Dict key cannot be a bool.')
            else:
                key_str = dump_compact(key, none_edge=True, root=False)

            value_str = '~' if value is None else dump_compact(value, none_edge=True, root=False)
            pairs.append(f'{key_str}:{value_str}')

        return '{' + ':'.join(pairs) + '}'

    raise ValueError(f'Cannot serialize value of type {type(value).__name__!r}.')

