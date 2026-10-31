from __future__ import annotations


__all__ = [
    'Call',
    'StringWithCalls',
    'CallDecodeError',
    'ArgsDecodeError',
    'CallEncodeError',
    'ArgsEncodeError',
    'ArgsDecoder',
    'ArgsEncoder',
    'CallDecoder',
    'CallEncoder',
    'call_encoder',
    'call_decoder',
    'args_encoder',
    'args_decoder',
]

import json
import string
import keyword
import unicodedata
from typing import Any, Mapping, NoReturn
from dataclasses import dataclass
from json import JSONDecodeError
from collections.abc import Sequence


def _parse_constant(_: Any) -> NoReturn:
    raise JSONDecodeError('', '', 0)


_TOKEN_ALLOWED_CHARS = frozenset(string.ascii_letters + string.digits + '_')
_JSON_DECODER = json.JSONDecoder(strict=False, parse_constant=_parse_constant)
_JSON_ENCODER = json.JSONEncoder(ensure_ascii=False, allow_nan=False)

type DecodedTypes = (
    str
    | bool
    | int
    | float
    | None
    | Call
    | tuple['DecodedTypes', ...]
    | frozendict['DecodedTypes', 'DecodedTypes']
)


type EncodableTypes = (
    DecodedTypes | Sequence['EncodableTypes'] | Mapping['DecodedTypes', 'EncodableTypes']
)


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[DecodedTypes, ...]
    kwargs: frozendict[str, DecodedTypes]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f'Call name must be a string, not {type(self.name)}.')
        if not self.name:
            raise ValueError('Call name cannot be empty.')

        for index, char in enumerate(self.name):
            if char not in _TOKEN_ALLOWED_CHARS:
                raise ValueError(
                    f'Call name {self.name!r} contains not allowed char {char!r} at position '
                    f"{index}. Call name can only contain ASCII letters, digits and '_'.",
                )

    def encode(self) -> str:
        return call_encoder.encode(self)


@dataclass(frozen=True)
class StringWithCalls:
    string: str
    decoded: tuple[str | Call, ...]
    call_spans: frozendict[tuple[int, int], Call]


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
_BARE_VALUE_STOP = frozenset(']}),=:')


class ArgsEncoder:
    _BARE_VALUE_FORBIDDEN = _BARE_VALUE_FORBIDDEN | _BARE_VALUE_STOP
    _JSON_ENCODER = _JSON_ENCODER
    _JSON_DECODER = _JSON_DECODER

    def encode(
        self, positional: Sequence[EncodableTypes], keyword: Mapping[str, EncodableTypes]
    ) -> str:
        args = [self.encode_value(i) for i in positional]
        if keyword:
            args.append(self.encode_kw(keyword))
        args_str = ', '.join(args)
        return f'({args_str})'

    def encode_value(self, value: EncodableTypes) -> str:
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

    def encode_kw(self, kw: Mapping[str, EncodableTypes]) -> str:
        normalized = {}
        for k, v in kw.items():
            k = unicodedata.normalize('NFKC', k)
            if k in normalized:
                raise ArgsEncodeError(f'Duplicate key {k!r} in keyword arguments.')
            normalized[k] = v

        encoded = [self.encode_kw_value(k, v) for k, v in normalized.items()]
        return ', '.join(encoded)

    def encode_kw_value(self, key: str, val: EncodableTypes) -> str:
        str_key = self.encode_kw_key(key)
        str_val = self.encode_value(val)
        return f'{str_key} = {str_val}'

    def encode_kw_key(self, val: str) -> str:
        if not isinstance(val, str):
            raise ArgsEncodeError(
                f'Cannot encode keyword argument name {val!r}. '
                f'Expected a string, got {type(val)!r}.'
            )

        val = unicodedata.normalize('NFKC', val)
        if not val.isidentifier() or keyword.iskeyword(val):
            raise ArgsEncodeError(f'Keyword argument name {val!r} is not valid.')
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

    def encode_sequence(self, value: Sequence[EncodableTypes]) -> str:
        result = []
        for i in value:
            result.append(self.encode_value(i))

        return f'[{", ".join(result)}]'

    def encode_mapping(self, value: Mapping[EncodableTypes, EncodableTypes]) -> str:
        result = []
        for k, v in value.items():
            str_k = self.encode_value(k)
            str_v = self.encode_value(v)
            result.append(f'{str_k}: {str_v}')
        return f'{{{", ".join(result)}}}'


args_encoder = ArgsEncoder()


class ArgsDecoder:
    _JSON_DECODER = _JSON_DECODER

    def raw_decode(
        self, value: str, pos: int = 0
    ) -> tuple[tuple[DecodedTypes, ...], frozendict[str, DecodedTypes], int]:
        if pos >= len(value):
            self._error(f'Position {pos} is out of string length {len(value)}', pos)

        if value[pos] != '(':
            self._error(f'`pos` must point to start of an args list `(`, got {value[pos]!r}.', pos)
        pos += 1
        pos = self._consume_spaces(value, pos)

        if pos >= len(value):
            self._error('Unexpected end of string. Expected args list closure `)`.', pos)
        if value[pos] == ')':
            return (), frozendict(), pos + 1

        positional: list[DecodedTypes] = []
        keyword: dict[str, DecodedTypes] = {}
        keyword_mode = False
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
                self._error('Unexpected end of string. Expected args list closure `)`.', pos)

            if not keyword_mode and value[pos] == '=':
                keyword_mode = True
                pos = start
                # we were parsing token as any type of value before.
                # now, with keyword_mode = True we will parse it as keyword argument name.
                continue

            if not keyword_mode:
                positional.append(current)

            if value[pos] == ')':
                break

            if value[pos] != ',':
                self._error(f'Unexpected char {value[pos]!r}. Expected args separator `,`.', pos)

            pos += 1
            pos = self._consume_spaces(value, pos)

        return tuple(positional), frozendict(keyword), pos + 1

    def decode_value(self, string: str, pos: int) -> tuple[DecodedTypes, int]:
        if pos >= len(string):
            self._error('Unexpected end of string. Expected value.', pos)

        result: DecodedTypes
        if string[pos] == '"':
            result, pos = self.decode_enquoted_value(string, pos)
        elif string[pos] == '[':
            result, pos = self.decode_sequence(string, pos)
        elif string[pos] == '{':
            result, pos = self.decode_mapping(string, pos)
        elif string[pos] == '$':
            result, pos = call_decoder.raw_decode(string, pos)
        else:
            result, pos = self.decode_bare_value(string, pos)
        return result, self._consume_spaces(string, pos)

    def decode_kw_value(self, string: str, pos: int) -> tuple[str, DecodedTypes, int]:
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

    def decode_mapping(
        self, string: str, pos: int
    ) -> tuple[frozendict[DecodedTypes, DecodedTypes], int]:
        pos += 1  # skip {
        pos = self._consume_spaces(string, pos)
        if pos >= len(string):
            self._error("Unexpected end of string. Expected end of a  mapping ('}').", pos)
        if string[pos] == '}':
            return frozendict(), pos + 1

        result: dict[DecodedTypes, DecodedTypes] = {}
        while True:
            start = pos
            key, pos = self.decode_value(string, pos)
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

        return frozendict(result), pos + 1

    def decode_sequence(self, string: str, pos: int) -> tuple[tuple[DecodedTypes, ...], int]:
        pos += 1  # skip [
        pos = self._consume_spaces(string, pos)
        if pos >= len(string):
            self._error("Unexpected end of string. Expected end of sequence (']').", pos)

        if string[pos] == ']':
            return (), pos + 1

        result: list[DecodedTypes] = []
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

        return tuple(result), pos + 1

    def decode_bare_value(
        self,
        string: str,
        pos: int,
        json_decode: bool = True,
        allow_spaces: bool = True,
    ) -> tuple[Any, int]:
        start = pos

        while True:
            if pos >= len(string):
                self._error('Unexpected end of string. Expected end of args list `)`.', pos)
            if not allow_spaces and string[pos].isspace():
                break
            if string[pos] in _BARE_VALUE_STOP:
                break
            if string[pos] in _BARE_VALUE_FORBIDDEN:
                self._error(f'Forbidden char {string[pos]!r} in bare value.', pos)
            pos += 1

        stop = pos

        if start == stop:
            self._error('Empty bare value.', pos)

        val = string[start:stop].strip()
        if json_decode:
            try:
                return self._JSON_DECODER.decode(val), pos
            except json.JSONDecodeError:
                pass
        return val, pos

    def decode_kw_key(self, string: str, pos: int) -> tuple[str, int]:
        start = pos
        result, pos = self.decode_bare_value(string, pos, json_decode=False, allow_spaces=False)
        result = unicodedata.normalize('NFKC', result)
        if not result.isidentifier() or keyword.iskeyword(result):
            self._error('Invalid keyword argument name.', pos=start)
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
    def encode(self, call: Call) -> str:
        encoded_args = args_encoder.encode(call.args, call.kwargs)
        return f'${call.name}{encoded_args}'


call_encoder = CallEncoder()


class CallDecoder:
    def raw_decode(self, string: str, pos: int = 0) -> tuple[Call, int]:
        if pos >= len(string):
            raise CallDecodeError(
                msg=f'Position {pos} is out of string length {len(string)}', pos=pos
            )

        if string[pos] != '$':
            raise CallDecodeError(msg='`pos` must point to start of a call.', pos=pos)

        pos += 1
        start = pos
        while True:
            if pos >= len(string):
                break

            char = string[pos]
            if char == '(' or char.isspace() or char not in _TOKEN_ALLOWED_CHARS:
                break
            pos += 1

        if pos == start:
            raise CallDecodeError(msg='Unexpected end of call. Expected call name.', pos=start)

        name = string[start:pos]

        if pos < len(string) and string[pos] == '(':
            args, kwargs, pos = args_decoder.raw_decode(string, pos)
            return Call(name=name, args=args, kwargs=kwargs), pos
        return Call(name=name, args=(), kwargs=frozendict()), pos

    def extract_calls(self, string: str) -> StringWithCalls:
        result: list[str | Call] = []
        spans: dict[tuple[int, int], Call] = {}
        buffer: list[str] = []

        pos = 0

        while pos < len(string):
            if string[pos] != '$':
                buffer.append(string[pos])
                pos += 1
                continue

            if string[pos : pos + 2] == '$$':
                buffer.append('$')
                pos += 2
                continue

            call, new_pos = self.raw_decode(string, pos)

            if buffer:
                result.append(''.join(buffer))
                buffer.clear()
            result.append(call)
            spans[(pos, new_pos)] = call
            pos = new_pos

        if buffer:
            result.append(''.join(buffer))
            buffer.clear()
        return StringWithCalls(string=string, decoded=tuple(result), call_spans=frozendict(spans))


call_decoder = CallDecoder()
