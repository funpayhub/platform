from __future__ import annotations

from typing import Any, NoReturn
from json import JSONDecoder, JSONEncoder, JSONDecodeError
from collections.abc import Set


_OBJ_SEP = ','
_COLLECTIONS_OPENINGS = frozenset('[{')
_SEQ_CLOSING = ']'
_MAPPING_CLOSING = '}'
_MAPPING_KEY_VAL_SEP = ':'

_MUST_BE_QUOTED = frozenset(['"', _OBJ_SEP])
_MUST_BE_QUOTED_MAPPING_KEY = _MUST_BE_QUOTED - {_OBJ_SEP} | {_MAPPING_KEY_VAL_SEP}
_MUST_BE_QUOTED_MAPPING_VALUE = _MUST_BE_QUOTED | {_MAPPING_CLOSING}
_MUST_BE_QUOTED_SEQ = _MUST_BE_QUOTED | {_SEQ_CLOSING}
_MUST_BE_QUOTED_ROOT_SEQ = _MUST_BE_QUOTED

_MUST_BE_QUOTED_IF_FIRST = _COLLECTIONS_OPENINGS
_MUST_BE_QUOTED_IF_FIRST_IN_MAPPING_KEY = _MUST_BE_QUOTED_IF_FIRST | {'}'}


INSIDE_SEQ_MODE = 1
INSIDE_ROOT_SEQ_MODE = 2
INSIDE_MAPPING_KEY_MODE = 3
INSIDE_MAPPING_VALUE_MODE = 4
COMMON_MODE = 5


_MUST_BE_QUOTED_BY_MODE = {
    COMMON_MODE: _MUST_BE_QUOTED,
    INSIDE_ROOT_SEQ_MODE: _MUST_BE_QUOTED_ROOT_SEQ,
    INSIDE_SEQ_MODE: _MUST_BE_QUOTED_SEQ,
    INSIDE_MAPPING_KEY_MODE: _MUST_BE_QUOTED_MAPPING_KEY,
    INSIDE_MAPPING_VALUE_MODE: _MUST_BE_QUOTED_MAPPING_VALUE,
}

_MUST_BE_QUOTED_IF_FIRST_BY_MODE = {
    COMMON_MODE: _MUST_BE_QUOTED_IF_FIRST,
    INSIDE_ROOT_SEQ_MODE: _MUST_BE_QUOTED_IF_FIRST,
    INSIDE_SEQ_MODE: _MUST_BE_QUOTED_IF_FIRST,
    INSIDE_MAPPING_KEY_MODE: _MUST_BE_QUOTED_IF_FIRST_IN_MAPPING_KEY,
    INSIDE_MAPPING_VALUE_MODE: _MUST_BE_QUOTED_IF_FIRST,
}

_JSON_ENCODER = JSONEncoder(ensure_ascii=False, allow_nan=False)
_JSON_DECODER = JSONDecoder()


def _can_dump_string_without_quotes(
    value: str,
    quote_if_first_is: Set[str] = _COLLECTIONS_OPENINGS,
    quote_if_contains: Set[str] = _MUST_BE_QUOTED,
) -> bool:
    if not value:
        return False

    if value[0] in quote_if_first_is:
        return False

    if any(char in value for char in quote_if_contains):
        return False

    if value == '^':
        return False

    try:
        _JSON_DECODER.raw_decode(value)
    except JSONDecodeError:
        return True
    else:
        return False


def dump_compact(value: Any, *, root: bool = True, inside_mode: int = COMMON_MODE) -> str:
    if isinstance(value, bool):
        return '1' if value else '0'
    if value is None:
        return ''
    if type(value) in (int, float):
        return _JSON_ENCODER.encode(value)

    if isinstance(value, str):
        if not value:
            return '^'

        must_be_quoted = _MUST_BE_QUOTED_BY_MODE[inside_mode]
        must_be_quoted_if_first = _MUST_BE_QUOTED_IF_FIRST_BY_MODE[inside_mode]
        if _can_dump_string_without_quotes(
            value, quote_if_first_is=must_be_quoted_if_first, quote_if_contains=must_be_quoted
        ):
            return _JSON_ENCODER.encode(value)[1:-1]
        return _JSON_ENCODER.encode(value)

    if isinstance(value, tuple | list):
        if len(value) == 1 and value[0] is None:
            value_str = '~'
        elif len(value) == 1 and value[0] == '~':
            value_str = '"~"'
        else:
            value_str = _OBJ_SEP.join(
                [
                    dump_compact(
                        i,
                        root=False,
                        inside_mode=INSIDE_ROOT_SEQ_MODE if root else INSIDE_SEQ_MODE,
                    )
                    for i in value
                ]
            )

        return f'{_OBJ_SEP}{value_str}' if root else f'[{value_str}]'

    if isinstance(value, dict):
        pairs = []
        for key, value in value.items():
            if key is None:
                key_str = ''
            elif isinstance(key, dict):
                raise ValueError('Dict key cannot be another dict.')
            elif isinstance(key, bool):
                raise ValueError('Dict key cannot be a bool.')
            else:
                key_str = dump_compact(key, root=False, inside_mode=INSIDE_MAPPING_KEY_MODE)
            val_str = dump_compact(value, root=False, inside_mode=INSIDE_MAPPING_VALUE_MODE)

            pairs.append(f'{key_str}{_MAPPING_KEY_VAL_SEP}{val_str}')

        return '{' + _OBJ_SEP.join(pairs) + '}'

    raise ValueError(f'Cannot serialize value of type {type(value).__name__!r}.')


class CompactFormatDecodeError(ValueError):
    pass


class CompactDecoder:
    __slots__ = ('value', 'pos')

    def __init__(self, value: str) -> None:
        self.value = value
        self.pos = 0

    def decode(self) -> Any:
        if not self.value:
            return None

        if self.value[0] == _OBJ_SEP:
            self.pos += 1
            result = self._parse_root_sequence()
        else:
            result = self._parse_value()

        if self.pos < len(self.value):
            self._error('Unexpected trailing data.')

        return result

    def _parse_value(self, inside_mode: int = COMMON_MODE, immutable: bool = False):
        if self.pos >= len(self.value):
            return None

        if self.value[self.pos] == '"':
            return self._parse_quoted_string()
        if self.value[self.pos] == '[':
            return self._parse_sequence(inside_mode=inside_mode, immutable=immutable)
        if self.value[self.pos] == '{':
            return self._parse_mapping(inside_mode=inside_mode, immutable=immutable)
        return self._parse_bare_value(inside_mode=inside_mode, immutable=immutable)

    def _parse_quoted_string(self) -> str:
        try:
            value, end = _JSON_DECODER.raw_decode(self.value, self.pos)
        except JSONDecodeError as e:
            self._error('Not a valid JSON string.', pos=e.pos)

        if not isinstance(value, str):
            self._error(f'Expected JSON string, but got {type(value).__name__!r}.')

        self.pos = end
        return value

    def _parse_root_sequence(self) -> list[Any]:
        if self.pos >= len(self.value):
            return []

        if len(self.value) == 2 and self.value[self.pos] == '~':
            self.pos += 1
            return [None]

        result = []
        while True:
            result.append(self._parse_value(inside_mode=INSIDE_ROOT_SEQ_MODE))
            if self.pos >= len(self.value):
                break

            if self.value[self.pos] != _OBJ_SEP:
                self._error(
                    f'Expected obj separator ({_OBJ_SEP!r}), got {self.value[self.pos]!r}',
                    self.pos,
                )

            self.pos += 1

        return result

    def _parse_sequence(
        self, inside_mode: int = COMMON_MODE, immutable: bool = False
    ) -> list[Any] | tuple[Any, ...]:
        if self._consume_next(']'):  # []
            return () if immutable else []

        if self._consume_next('~]'):
            return (None,) if immutable else [None]

        result = []

        self.pos += 1
        while True:
            result.append(self._parse_value(inside_mode=INSIDE_SEQ_MODE, immutable=immutable))
            if self.pos >= len(self.value):
                self._error("Unterminated sequence. Expected end of sequence (']'), but got EOF.")

            curr_char = self.value[self.pos]
            if curr_char == ']':
                break

            if curr_char != _OBJ_SEP:
                self._error(f'Expected obj separator ({_OBJ_SEP!r}), got {curr_char!r}', self.pos)
            self.pos += 1

        self.pos += 1
        return tuple(result) if immutable else result

    def _parse_mapping(
        self, inside_mode: int = COMMON_MODE, immutable: bool = False
    ) -> dict[Any, Any]:
        if self._consume_next('}'):
            return {}

        self.pos += 1  # skip {

        result = {}
        while True:
            key = self._parse_mapping_key()
            curr_char = self.value[self.pos]
            if curr_char != _MAPPING_KEY_VAL_SEP:
                self._error(
                    f'Expected key-value separator ({_MAPPING_KEY_VAL_SEP!r}), got {curr_char!r}.'
                )
            self.pos += 1

            if key in result:
                self._error('Key duplicate.')  # todo

            value = self._parse_value(inside_mode=INSIDE_MAPPING_VALUE_MODE, immutable=immutable)
            result[key] = value

            if self.pos >= len(self.value):
                self._error(
                    f'Unexpected EOF. '
                    f"Expected end of mapping ('}}') or obj separator ({_OBJ_SEP!r})"
                )

            curr_char = self.value[self.pos]
            if curr_char == '}':
                break

            if curr_char != _OBJ_SEP:
                self._error(f'Expected obj separator ({_OBJ_SEP!r}), got {curr_char!r}', self.pos)
            self.pos += 1

        self.pos += 1
        return result

    def _parse_mapping_key(self) -> Any:
        if self.pos >= len(self.value):
            self._error('Unexpected EOF. Expected mapping key.')

        if self.value[self.pos] == '}':
            self._error('Unexpected end of mapping. Expected key.', pos=self.pos - 1)

        start = self.pos
        val = self._parse_value(inside_mode=INSIDE_MAPPING_KEY_MODE, immutable=True)

        if isinstance(val, dict):
            self._error('Mapping cannot be a key in mapping.', pos=start)

        return val

    def _parse_bare_value(self, inside_mode: int = COMMON_MODE, immutable: bool = False) -> Any:
        start = self.pos

        while self.pos < len(self.value):
            char = self.value[self.pos]
            if char in _MUST_BE_QUOTED_BY_MODE[inside_mode]:
                break

            self.pos += 1

        token = self.value[start : self.pos]
        if not token:
            return None
        if token == '^':
            return ''

        try:
            return _JSON_DECODER.decode(token)
        except JSONDecodeError:
            try:
                return _JSON_DECODER.decode(f'"{token}"')
            except JSONDecodeError:
                self._error('Invalid JSON string.')

    def _error(self, error_text: str, pos: int | None = None) -> NoReturn:
        raise CompactFormatDecodeError(
            f'Decoding error at {self.pos if pos is None else pos}: {error_text}'
        )

    def _consume_next(self, char: str) -> bool:
        if self.pos >= len(self.value):
            return False

        if self.value.startswith(char, self.pos + 1):
            self.pos += len(char) + 1
            return True
        return False


def loads_compact(value: str) -> Any:
    decoder = CompactDecoder(value)
    return decoder.decode()
