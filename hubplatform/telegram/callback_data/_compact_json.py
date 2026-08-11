from __future__ import annotations

import json
from typing import Any, NoReturn


_SPECIAL_CHARS = frozenset(':}]"')
_SPECIAL_FIRST_CHARS = frozenset('[{')


def _can_dump_string_bare(value: str) -> bool:
    """Whether a string can be serialized without JSON quotes."""
    if not value:
        return False

    if value[0] in _SPECIAL_FIRST_CHARS:
        return False

    value_set = frozenset(value)

    if any(char in _SPECIAL_CHARS for char in value_set):
        return False

    try:
        json.loads(value)
    except json.JSONDecodeError, ValueError:
        return True

    return False


def _compact_dumps(value: Any, root: bool = True) -> str:
    if isinstance(value, str):
        if _can_dump_string_bare(value):
            return value

        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, bool):
        return '1' if value else '0'
    if value is None:
        return ''

    if type(value) in (int, float):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    if isinstance(value, list | tuple):
        if len(value) == 1 and value[0] is None:
            val_str = '~'
        elif len(value) == 1 and value[0] == '~':
            val_str = '"~"'
        else:
            val_str = ':'.join(_compact_dumps(item, root=False) for item in value)

        return f'[{val_str}]' if not root else f':{val_str}'

    if isinstance(value, dict):
        items = []

        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f'Compact JSON object key must be str, got {type(key).__name__}.')

            items.append(f'{_compact_dumps(key, root=False)}:{_compact_dumps(item, root=False)}')

        return '{' + ':'.join(items) + '}'

    raise TypeError(f'Value of type {type(value).__name__} is not JSON-compatible.')


class CompactDecodeError(ValueError):
    pass


class _CompactDecoder:
    def __init__(self, data: str) -> None:
        self.data = data
        self.pos = 0
        self._json_decoder = json.JSONDecoder()

    def decode(self) -> Any:
        if not self.data:
            return None

        # Root list is explicitly marked with ":".
        if self.data[0] == ':':
            self.pos = 1
            result = self._parse_sequence(end=None)

            if self.pos != len(self.data):
                self._error('Unexpected trailing data.')
            return result

        result = self._parse_value()

        if self.pos != len(self.data):
            self._error(f'Unexpected character {self.data[self.pos]!r}')
        return result

    def _parse_value(self) -> Any:
        if self.pos >= len(self.data):
            return None

        char = self.data[self.pos]

        if char == '"':
            return self._parse_quoted_string()

        if char == '[':
            return self._parse_list()

        if char == '{':
            return self._parse_dict()

        return self._parse_bare_value()

    def _parse_quoted_string(self) -> str:
        start = self.pos

        try:
            value, end = self._json_decoder.raw_decode(self.data, self.pos)
        except json.JSONDecodeError as e:
            self._error(f'Invalid JSON string: {e.msg}', pos=e.pos)

        if not isinstance(value, str):
            self._error('Expected JSON string', pos=start)

        self.pos = end
        return value

    def _parse_bare_value(self) -> Any:
        start = self.pos

        while self.pos < len(self.data):
            char = self.data[self.pos]

            if char in ':]}':
                break

            self.pos += 1

        token = self.data[start : self.pos]

        if not token or token == '~':
            return None

        try:
            return json.loads(token)
        except json.JSONDecodeError, ValueError:
            return token

    def _parse_sequence(self, *, end: str | None) -> list[Any]:
        result: list[Any] = []

        if end is not None and self._consume(end):
            return result

        if end is None and self.pos >= len(self.data):
            return result

        expect_value = True

        while True:
            if self.pos >= len(self.data):
                if end is not None:
                    self._error(f'Unterminated sequence, expected {end!r}')

                if expect_value:
                    result.append(None)

                return result

            if end is not None and self.data[self.pos] == end:
                if expect_value:
                    result.append(None)

                self.pos += 1
                return result

            if expect_value:
                if self.data[self.pos] == ':':
                    result.append(None)
                    self.pos += 1
                    continue

                result.append(self._parse_value())
                expect_value = False
                continue

            if end is not None and self._consume(end):
                return result

            if self._consume(':'):
                expect_value = True
                continue

            expected = f"':' or {end!r}" if end is not None else "':'"
            self._error(f'Expected {expected}')

    def _parse_list(self) -> list[Any]:
        self.pos += 1  # [
        return self._parse_sequence(end=']')

    def _parse_dict(self) -> dict[str, Any]:
        self.pos += 1  # {

        result: dict[str, Any] = {}

        if self._consume('}'):
            return result

        while True:
            if self.pos >= len(self.data):
                self._error('Unterminated object')

            key = self._parse_dict_key()

            self._expect(':')

            # Empty value:
            #
            # {a:}
            # {a::b:c}
            if self.pos >= len(self.data):
                self._error('Unterminated object')

            if self.data[self.pos] == '}':
                result[key] = None
                self.pos += 1
                return result

            if self.data[self.pos] == ':':
                result[key] = None
                self.pos += 1
                continue

            result[key] = self._parse_value()

            if self._consume('}'):
                return result

            # Separator between key/value pairs.
            self._expect(':')

    def _parse_dict_key(self) -> str:
        if self.pos >= len(self.data):
            self._error('Expected object key')

        if self.data[self.pos] == '"':
            return self._parse_quoted_string()

        start = self.pos

        while self.pos < len(self.data):
            char = self.data[self.pos]

            if char == ':':
                break

            if char in '[]{}"\\':
                self._error(f'Unexpected character {char!r} inside object key')

            self.pos += 1

        if self.pos == start:
            self._error('Empty bare object key')

        return self.data[start : self.pos]

    def _consume(self, char: str) -> bool:
        if self.pos < len(self.data) and self.data[self.pos] == char:
            self.pos += 1
            return True

        return False

    def _expect(self, char: str) -> None:
        if self._consume(char):
            return

        if self.pos >= len(self.data):
            actual = '<EOF>'
        else:
            actual = repr(self.data[self.pos])

        self._error(f'Expected {char!r}, got {actual}')

    def _error(self, message: str, *, pos: int | None = None) -> NoReturn:
        raise CompactDecodeError(f'{message} at position {pos if pos is not None else self.pos}')


def _compact_loads(data: str) -> Any:
    return _CompactDecoder(data).decode()


if __name__ == '__main__':
    print(_compact_dumps([None]))
    print(_compact_dumps([]))
    print(_compact_dumps([[None]]))
