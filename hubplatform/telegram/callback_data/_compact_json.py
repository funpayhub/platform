import json
from typing import Any, NoReturn

_COMPACT_STRING_SPECIAL_CHARS = frozenset(',:%[]{}"\\')


def _can_dump_string_bare(value: str) -> bool:
    """Whether a string can be serialized without JSON quotes."""
    if not value:
        return False

    if any(char in _COMPACT_STRING_SPECIAL_CHARS for char in value):
        return False

    try:
        json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return True

    return False


def _compact_dumps(value: Any) -> str:
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
        return '[' + ','.join(_compact_dumps(item) for item in value) + ']'

    if isinstance(value, dict):
        items = []

        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f'Compact JSON object key must be str, got {type(key).__name__}.')

            items.append(f'{json.dumps(key)}:{_compact_dumps(item)}')

        return '{' + ','.join(items) + '}'

    raise TypeError(f'Value of type {type(value).__name__} is not JSON-compatible.')


class CompactDecodeError(ValueError): pass


class _CompactParser:
    def __init__(self, data: str) -> None:
        self.data = data
        self.pos = 0
        self._json_decoder = json.JSONDecoder()

    def parse(self) -> Any:
        if not self.data:
            return None

        value = self._parse_value()

        if self.pos != len(self.data):
            self._error(f'Unexpected character {self.data[self.pos]!r}')

        return value

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
            value, self.pos = self._json_decoder.raw_decode(
                self.data,
                self.pos,
            )
        except json.JSONDecodeError as e:
            self._error('Invalid JSON string', pos=e.pos)

        if not isinstance(value, str):
            self._error('Expected JSON string', pos=start)

        return value

    def _parse_bare_value(self) -> Any:
        start = self.pos

        while self.pos < len(self.data):
            char = self.data[self.pos]

            if char in ',]}':
                break

            if char in _COMPACT_STRING_SPECIAL_CHARS:
                self._error(f'Unexpected special character {char!r} in bare value')

            self.pos += 1

        token = self.data[start:self.pos]

        if not token:
            return None

        try:
            return json.loads(token)
        except (json.JSONDecodeError, ValueError):
            return token

    def _parse_list(self) -> list[Any]:
        self.pos += 1  # [

        result: list[Any] = []

        if self._consume(']'):
            return result

        expect_value = True

        while True:
            if self.pos >= len(self.data):
                self._error('Unterminated list')

            if expect_value:
                if self.data[self.pos] == ']':
                    result.append(None)
                    self.pos += 1
                    return result

                if self.data[self.pos] == ',':
                    result.append(None)
                    self.pos += 1
                    continue

                result.append(self._parse_value())
                expect_value = False
                continue

            if self._consume(']'):
                return result

            if self._consume(','):
                expect_value = True
                continue

            self._error(
                "Expected ',' or ']' in list"
            )

    def _parse_dict(self) -> dict[str, Any]:
        self.pos += 1  # {

        result: dict[str, Any] = {}

        if self._consume('}'):
            return result

        while True:
            if self.pos >= len(self.data):
                self._error('Unterminated object')

            if self.data[self.pos] != '"':
                self._error('Object key must be a quoted JSON string')

            key = self._parse_quoted_string()

            if not self._consume(':'):
                self._error("Expected ':' after object key")

            if self.pos >= len(self.data):
                self._error('Unterminated object')

            if self.data[self.pos] in ',}':
                value = None
            else:
                value = self._parse_value()

            result[key] = value

            if self._consume('}'):
                return result

            if self._consume(','):
                continue

            self._error("Expected ',' or '}' in object")

    def _consume(self, char: str) -> bool:
        if (self.pos < len(self.data) and self.data[self.pos] == char):
            self.pos += 1
            return True

        return False

    def _error(self, message: str, *, pos: int | None = None) -> NoReturn:
        if pos is None:
            pos = self.pos

        raise CompactDecodeError(f'{message} at position {pos}')


def _compact_loads(data: str) -> Any:
    return _CompactParser(data).parse()

