from __future__ import annotations

import json
from typing import Any, NoReturn
from json import JSONDecoder, JSONDecodeError


_OPEN_SPECIAL = frozenset('[{')
_SPECIAL = frozenset('}]:"')


def _can_dump_string_without_quotes(
    value: str,
) -> bool:
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
    except json.JSONDecodeError, ValueError:
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
                key_str = ''
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


class CompactFormatDecodeError(ValueError):
    pass


class CompactDecoder:
    _BARE_VALUE_STOP_LITERALS = frozenset('}]:')

    def __init__(self, value: str) -> None:
        self.value = value
        self.pos = 0
        self.json_decoder = JSONDecoder()

    def decode(self) -> Any:
        if not self.value:
            return None

        if self.value[0] == ':':
            self.pos += 1
            result = self._parse_root_sequence()
        else:
            result = self._parse_value()

        if self.pos < len(self.value):
            self._error('Unexpected trailing data.')

        return result

    def _parse_value(self, immutable: bool = False):
        if self.current_char is None:
            return None

        if self.value[self.pos] == '"':
            return self._parse_quoted_string()
        if self.value[self.pos] == '[':
            return self._parse_sequence(root=False, immutable=immutable)
        if self.value[self.pos] == '{':
            return self._parse_mapping()
        return self._parse_bare_value()

    def _parse_quoted_string(self) -> str:
        try:
            value, end = self.json_decoder.raw_decode(self.value, self.pos)
        except JSONDecodeError as e:
            self._error('Not a valid JSON string.', pos=e.pos)

        if not isinstance(value, str):
            self._error(f'Expected JSON string, but got {type(value).__name__!r}.')

        self.pos = end
        return value

    def _parse_sequence(
        self, root: bool = False, immutable: bool = False
    ) -> list[Any] | tuple[Any]:
        return (
            self._parse_root_sequence()
            if root
            else self._parse_non_root_sequence(immutable=immutable)
        )

    def _parse_root_sequence(self) -> list[Any]:
        if self.current_char is None:
            return []

        if len(self.value) == 2 and self.current_char == '~':
            self.pos += 1
            return [None]

        result = []
        while True:
            result.append(self._parse_value())
            if self.current_char is None:
                break

            self.pos += 1

        return result

    def _parse_non_root_sequence(self, immutable: bool = False) -> list[Any] | tuple[Any, ...]:
        if self._consume_next(']'):  # []
            return [] if not immutable else ()

        if self._consume_next('~]'):
            return [None] if not immutable else (None,)

        result = []

        self.pos += 1
        while True:
            result.append(self._parse_value(immutable=immutable))
            if self.current_char is None:
                self._error("Unterminated sequence. Expected end of sequence (']'), but got EOF.")

            if self.value[self.pos] == ']':
                break

            if not self.value[self.pos] == ':':
                self._error("Expected separator ':'.", self.pos + 1)
            self.pos += 1

        self.pos += 1
        return result if not immutable else tuple(result)

    def _parse_mapping(self) -> dict[Any, Any]:
        if self._consume_next('}'):
            return {}

        if self._consume_next('~}'):
            return {None: None}

        self.pos += 1

        result = {}
        while True:
            key = self._parse_mapping_key()
            if self.current_char != ':':
                self._error(f"Expected key-value separator (':'), got {self.current_char}.")
            self.pos += 1

            if key in result:
                self._error('Key duplicate.')  # todo

            value = self._parse_value()
            result[key] = value

            if self.current_char == '}':
                break

            if self.current_char != ':':
                self._error(f"Expected dict items separator (':'), got {self.current_char}.")
            self.pos += 1

        self.pos += 1
        return result

    def _parse_mapping_key(self) -> Any:
        if self._consume_next('~:'):
            self.pos -= 1
            return None

        if self._consume_next('}'):
            self._error('Unexpected end of mapping. Expected key.', pos=self.pos + 1)

        val = self._parse_value(immutable=True)
        return val

    def _parse_bare_value(self) -> Any:
        start = self.pos

        while self.pos < len(self.value):
            char = self.value[self.pos]
            if char in self._BARE_VALUE_STOP_LITERALS:
                break

            self.pos += 1

        token = self.value[start : self.pos]
        if not token:
            return None
        if token == '^':
            return ''

        try:
            return json.loads(token)
        except JSONDecodeError:
            return token

    def _error(self, error_text: str, pos: int | None = None) -> NoReturn:
        raise CompactFormatDecodeError(
            f'Decoding error at {self.pos if pos is None else pos}: {error_text}'
        )

    def _consume_next(self, char: str | None = None) -> bool:
        if self.pos >= len(self.value):
            return False
        if char is None:
            self.pos += 2
            return True

        next_char = self.pos + 1
        val = self.value[next_char : next_char + len(char)]
        if val == char:
            self.pos += len(char) + 1
            return True
        return False

    @property
    def current_char(self) -> str | None:
        if self.pos >= len(self.value):
            return None
        return self.value[self.pos]


def loads_compact(value: str) -> Any:
    decoder = CompactDecoder(value)
    return decoder.decode()
