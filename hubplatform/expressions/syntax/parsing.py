from __future__ import annotations


__all__ = [
    'CallDecodeError',
    'ArgsDecodeError',
    'CallEncodeError',
    'ArgsEncodeError',
    'ArgsDecoder',
    'CallDecoder',
    'CallEncoder',
    'call_encoder',
    'call_decoder',
    'args_encoder',
    'args_decoder',
]

import json
import string
from typing import Any, Mapping, NoReturn
from collections.abc import Set, Sequence

from hubplatform.expressions.syntax.types import Call, StringWithCalls


_TOKEN_ALLOWED_CHARS = frozenset(string.ascii_letters + string.digits + '_')


def _check_token(
    token: Any, name: str, exception_type: type[Exception] = ValueError, *args: Any, **kwargs: Any
) -> None:
    if not isinstance(token, str):
        raise exception_type(f'{name} must be a string, not {type(token)!r}.', *args, **kwargs)
    if not token:
        raise exception_type(f'{name} cannot be empty.', *args, **kwargs)
    for index, c in enumerate(token):
        if c not in _TOKEN_ALLOWED_CHARS:
            raise exception_type(
                f'{name} contains not allowed char {c!r} at position '
                f"{index}. {name} can only contain ASCII letters, digits and '_'.",
                *args,
                **kwargs,
            )
    if token[0].isdigit():
        raise exception_type(f'{name} cannot start with a digit.', *args, **kwargs)


class CallDecodeError(Exception):
    def __init__(self, pos: int, msg: str) -> None:
        self._pos = pos
        self._msg = msg

        super().__init__(msg)


class ArgsDecodeError(CallDecodeError):
    pass


class CallEncodeError(Exception):
    pass


class ArgsEncodeError(CallEncodeError):
    pass


_BARE_VALUE_FORBIDDEN = frozenset('[{("\\$')
_BARE_VALUE_STOP = frozenset(',=)]}:')


class ArgsEncoder:
    _BARE_VALUE_FORBIDDEN = _BARE_VALUE_FORBIDDEN | _BARE_VALUE_STOP
    _JSON_ENCODER = json.JSONEncoder()
    _JSON_DECODER = json.JSONDecoder()

    def encode(self, positional: Sequence[Any], keyword: dict[str, Any]) -> str:
        strfied = [self.encode_value(i) for i in positional] + [
            self.encode_kw_value(k, v) for k, v in keyword.items()
        ]
        return f'({", ".join(strfied)})'

    def encode_value(self, value: Any) -> str:
        if isinstance(value, str):
            return self.encode_string(value)
        if isinstance(value, int | float | bool) or value is None:
            return self.encode_int_float_bool_none(value)
        if isinstance(value, Sequence):
            return self.encode_sequence(value)
        if isinstance(value, Mapping):
            return self.encode_mapping(value)
        if isinstance(value, Call):
            return value.encode()
        raise TypeError('Unexpected value type.')  # todo

    def encode_kw_value(self, key: str, val: Any) -> str:
        str_key = self.encode_kw_key(key)
        str_val = self.encode_value(val)
        return f'{str_key} = {str_val}'

    def encode_kw_key(self, val: str) -> str:
        _check_token(val, 'Keyword arg name', CallEncodeError)
        return val

    def encode_string(self, value: str) -> str:
        if (
            not value
            or any(c in self._BARE_VALUE_FORBIDDEN for c in value)
            or value[0].isspace()
            or value[-1].isspace()
        ):
            return self._JSON_ENCODER.encode(value)

        try:
            self._JSON_DECODER.decode(value)
        except json.JSONDecodeError:
            return value
        return self._JSON_ENCODER.encode(value)

    def encode_int_float_bool_none(self, value: int | float | bool | None) -> str:
        if value is None:
            return 'null'
        if value is True:
            return 'true'
        if value is False:
            return 'false'
        return self._JSON_ENCODER.encode(value)

    def encode_sequence(self, value: Sequence[Any]) -> str:
        result = []
        for i in value:
            result.append(self.encode_value(i))

        return f'[{", ".join(result)}]'

    def encode_mapping(self, value: Mapping[str, Any]) -> str:
        result = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError('Mapping key must be a string!')  # todo

            str_k = self.encode_string(k)
            str_v = self.encode_value(v)
            result.append(f'{str_k}: {str_v}')
        return f'{{{", ".join(result)}}}'


args_encoder = ArgsEncoder()


class ArgsDecoder:
    _JSON_DECODER = json.JSONDecoder()

    def decode(self, value: str) -> tuple[list[Any], dict[str, Any]]:
        if not value:
            self._error('Empty value passed.', 0)
        if value[0] != '(':
            self._error("Args string must start with '('.", 0)

        positional, keyword, pos = self.raw_decode(value)
        if pos != len(value):
            self._error('Trailing data. Expected end of string.', pos)
        return positional, keyword

    def raw_decode(self, value: str, pos: int = 0) -> tuple[list[Any], dict[str, Any], int]:
        if pos >= len(value):
            return [], {}, pos

        if value[pos] != '(':
            return [], {}, pos
        pos += 1

        keyword_mode = False

        pos = self._consume_spaces(value, pos)
        if pos >= len(value):
            self._error("Unexpected end of string. Expected args closure (')').", pos)
        if value[pos] == ')':
            return [], {}, pos + 1

        positional = []
        keyword = {}
        while True:
            start = pos

            if keyword_mode:
                key, val, pos = self.decode_kw_value(value, pos)
                if key in keyword:
                    self._error(f'Duplicate keyword argument {key!r}.', pos=start)
                keyword[key] = val
            else:
                current, pos = self.decode_value(value, pos)

            if pos >= len(value):
                self._error("Unexpected end of string. Expected args closure (')').", pos)
            if not keyword_mode and value[pos] == '=':
                keyword_mode = True
                pos = start
                continue  # todo: parse again is not good

            if not keyword_mode:
                positional.append(current)

            if value[pos] == ')':
                break

            if value[pos] != ',':
                self._error(f"Unexpected char {value[pos]!r}. Expected args separator (',').", pos)

            pos += 1
            pos = self._consume_spaces(value, pos)

        return positional, keyword, pos + 1

    def decode_value(self, string: str, pos: int, simple_only: bool = False) -> tuple[Any, int]:
        if pos >= len(string):
            self._error('Unexpected end of string. Expected value.', pos)

        result: Any
        if string[pos] == '"':
            result, pos = self.decode_enquoted_value(string, pos)
        elif string[pos] == '[':
            if simple_only:
                self._error(
                    'Unexpected start of a sequence. Expected non-container types only.', pos
                )
            result, pos = self.decode_sequence(string, pos)
        elif string[pos] == '{':
            if simple_only:
                self._error(
                    'Unexpected start of a mapping. Expected non-container types only.', pos
                )
            result, pos = self.decode_mapping(string, pos)
        elif string[pos] == '$':
            if simple_only:
                self._error('Unexpected start of a call. Expected non-container types only.', pos)
            result, pos = call_decoder.raw_decode(string, pos)
        else:
            result, pos = self.decode_bare_value(string, pos)
        return result, self._consume_spaces(string, pos)

    def decode_kw_value(self, string: str, pos: int) -> tuple[str, Any, int]:
        key, pos = self.decode_kw_key(string, pos)
        pos = self._consume_spaces(string, pos)
        if pos >= len(string):
            self._error(
                f'Unexpected end of string. Expected value for keyword argument {key!r}.', pos
            )

        if string[pos] != '=':
            self._error(
                f'Unexpected char {string[pos]!r}. Expected keyword argument '
                f"name-value separator ('=').",
                pos,
            )
        pos += 1
        pos = self._consume_spaces(string, pos)
        value, pos = self.decode_value(string, pos)
        return key, value, pos

    def decode_enquoted_value(self, string: str, pos: int) -> tuple[str, int]:
        try:
            return self._JSON_DECODER.raw_decode(string, pos)
        except json.JSONDecodeError as e:
            self._error('Bad enquoted string.', pos=e.pos)

    def decode_mapping(self, string: str, pos: int) -> tuple[dict[Any, Any], int]:
        pos += 1  # skip {
        pos = self._consume_spaces(string, pos)
        if pos >= len(string):
            self._error("Unexpected end of string. Expected end of a  mapping ('}').", pos)
        if string[pos] == '}':
            return {}, pos + 1

        result = {}
        while True:
            start = pos
            key, pos = self.decode_value(string, pos, simple_only=True)
            if key in result:
                self._error(f'Duplicate mapping key {key!r}.', pos=start)
            if pos >= len(string):
                self._error(f'Unexpected end of string. Expected value for key {key!r}.', pos)
            if string[pos] != ':':
                self._error(
                    f"Unexpected char {string[pos]}. Expected key-value separator (':').", pos
                )
            pos += 1
            pos = self._consume_spaces(string, pos)

            value, pos = self.decode_value(string, pos)
            result[key] = value
            if pos >= len(string):
                self._error("Unexpected end of string. Expected end of a  mapping ('}').", pos)
            if string[pos] == '}':
                break
            if string[pos] != ',':
                self._error(
                    f"Unexpected char {string[pos]}. Expected key-value pairs separator (',').",
                    pos,
                )
            pos += 1
            pos = self._consume_spaces(string, pos)

        return result, pos + 1

    def decode_sequence(self, string: str, pos: int) -> tuple[list[Any], int]:
        pos += 1  # skip [
        pos = self._consume_spaces(string, pos)
        if pos >= len(string):
            self._error("Unexpected end of string. Expected end of sequence (']').", pos)

        if string[pos] == ']':
            return [], pos + 1

        result = []
        while True:
            value, pos = self.decode_value(string, pos)
            result.append(value)

            if pos >= len(string):
                self._error("Unexpected end of string. Expected end of sequence (']').", pos)
            if string[pos] == ']':
                break
            if string[pos] != ',':
                self._error(
                    f"Unexpected char {string[pos]!r}. Expected sequence item separator (',').",
                    pos,
                )
            pos += 1
            pos = self._consume_spaces(string, pos)

        return result, pos + 1

    def decode_bare_value(
        self,
        string: str,
        pos: int,
        json_decode: bool = True,
        allowed: Set[str] | None = None,
        allow_spaces: bool = True,
    ) -> tuple[Any, int]:
        start = pos

        while True:
            if pos >= len(string):
                self._error('Unexpected end of string. Expected end of bare value.', pos)
            if not allow_spaces and string[pos].isspace():
                break
            if string[pos] in _BARE_VALUE_STOP:
                break
            if string[pos] in _BARE_VALUE_FORBIDDEN:
                self._error(f'Forbidden char {string[pos]!r} in bare value.', pos)
            if allowed is not None and string[pos] not in allowed:
                self._error(f'Forbidden char {string[pos]!r} in bare value.', pos)
            pos += 1

        stop = pos

        if start == stop:
            self._error('Empty bare value.', pos)

        val = string[start:stop]
        if json_decode:
            try:
                return self._JSON_DECODER.decode(val), pos
            except json.JSONDecodeError:
                pass
        return val.strip(), pos

    def decode_kw_key(self, string: str, pos: int) -> tuple[str, int]:
        start = pos
        result, pos = self.decode_bare_value(
            string, pos, json_decode=False, allowed=_TOKEN_ALLOWED_CHARS, allow_spaces=False
        )
        if result[0].isdigit():
            self._error('Keyword name cannot start with a digit.', pos=start)
        return result, pos

    def _consume_spaces(self, value: str, pos: int) -> int:
        while True:
            if pos >= len(value):
                return pos
            if not value[pos].isspace():
                return pos
            pos += 1

    def _error(self, msg: str, pos: int) -> NoReturn:
        msg = f'Args parsing error at position {pos}: {msg}'
        raise ArgsDecodeError(pos=pos, msg=msg)


args_decoder = ArgsDecoder()


class CallEncoder:
    _ARGS_ENCODER = ArgsEncoder()

    def encode(self, call_name: str, args: Sequence[Any], kwargs: dict[str, Any]) -> str:
        _check_token(call_name, 'Call name', CallEncodeError)
        encoded_args = self._ARGS_ENCODER.encode(args, kwargs)
        return f'${call_name}{encoded_args}'


call_encoder = CallEncoder()


class CallDecoder:
    _ARGS_PARSER = ArgsDecoder()

    def raw_decode(self, string: str, pos: int = 0) -> tuple[Call | None, int]:
        initial_pos = pos
        if pos >= len(string):
            return None, initial_pos

        if string[pos] != '$':
            return None, initial_pos

        pos += 1

        start = pos
        while True:
            if pos >= len(string):
                break
            if string[pos].isspace():
                break
            if string[pos] == '(':
                break
            if string[pos] not in _TOKEN_ALLOWED_CHARS:
                raise CallDecodeError(
                    msg=f'Call name contains not allowed char {string[pos]!r}. '
                    f"Call names can only contain ASCII letters, digits and '_'.",
                    pos=pos,
                )
            pos += 1

        if pos == start:
            return None, initial_pos

        name = string[start:pos]
        if name[0].isdigit():
            raise CallDecodeError(msg='Call name cannot start with a digit.', pos=start)

        args, kwargs, pos = self._ARGS_PARSER.raw_decode(string, pos)

        return Call(name=name, args=args, kwargs=kwargs), pos

    def extract_calls(self, string: str) -> StringWithCalls:
        result: list[str | Call] = []
        spans: dict[tuple[int, int], Call] = {}
        text: list[str] = []

        def flush_text() -> None:
            if text:
                result.append(''.join(text))
                text.clear()

        pos = 0

        while pos < len(string):
            if string[pos] != '$':
                text.append(string[pos])
                pos += 1
                continue

            if string[pos : pos + 2] == '$$':
                text.append('$')
                pos += 2
                continue

            call, new_pos = self.raw_decode(string, pos)

            if call is None:
                text.append('$')
                pos += 1
                continue

            flush_text()
            result.append(call)
            spans[(pos, new_pos)] = call
            pos = new_pos

        flush_text()
        return StringWithCalls(string=string, decoded=result, call_spans=spans)


call_decoder = CallDecoder()
