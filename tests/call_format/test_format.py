from __future__ import annotations

from typing import Any

import pytest

from hubplatform.expressions.syntax import Call
from hubplatform.expressions.syntax.parsing import (
    _TOKEN_ALLOWED_CHARS,
    ArgsDecoder,
    ArgsEncoder,
    CallDecoder,
    ArgsDecodeError,
    CallDecodeError,
    CallEncodeError,
)


ENCODER = ArgsEncoder()
DECODER = ArgsDecoder()
CALL_DECODER = CallDecoder()

VALID_INITIAL_CHARS = sorted(char for char in _TOKEN_ALLOWED_CHARS if not char.isdigit())
VALID_TOKENS = [*VALID_INITIAL_CHARS, *(f'a{char}' for char in sorted(_TOKEN_ALLOWED_CHARS))]

ATOMS: list[Any] = [
    0,
    1,
    -1,
    12345678901234567890,
    0.0,
    -1.25,
    True,
    False,
    None,
    '',
    'plain',
    'two words',
    ' leading',
    'trailing ',
    '123',
    '-1.25',
    'true',
    'false',
    'null',
    'NaN',
    'Infinity',
    'привет',
    'line\nbreak',
    'tab\tinside',
    '"quoted"',
    'back\\slash',
    'a,b',
    'a=b',
    'a:b',
    '[value]',
    '{value}',
    '(value)',
]


def assert_args_decode_error(source: str, position: int, message: str) -> None:
    with pytest.raises(ArgsDecodeError) as exc_info:
        DECODER.decode(source)

    assert exc_info.value._pos == position
    assert message in str(exc_info.value)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        *[(value, value) for value in ATOMS],
        ([], []),
        ([1, 'two', None], [1, 'two', None]),
        ((1, 'two', None), [1, 'two', None]),
        ({}, {}),
        ({'key': 'value', 'empty': '', 'none': None}, {'key': 'value', 'empty': '', 'none': None}),
        (
            ['root', [1, True, None], {'nested': ['value', {'deep': -2.5}]}],
            ['root', [1, True, None], {'nested': ['value', {'deep': -2.5}]}],
        ),
    ],
)
def test_value_round_trip_as_positional_and_keyword(value: Any, expected: Any) -> None:
    encoded = ENCODER.encode([value], {'copy': value})

    positional, keyword = DECODER.decode(encoded)

    assert positional == [expected]
    assert keyword == {'copy': expected}


@pytest.mark.parametrize(
    'space', [chr(codepoint) for codepoint in range(0x110000) if chr(codepoint).isspace()]
)
def test_every_unicode_space_round_trips_at_string_boundaries_and_inside(space: str) -> None:
    values = [space, f'{space}value', f'value{space}', f'left{space}right']

    encoded = ENCODER.encode(values, {})

    assert DECODER.decode(encoded) == (values, {})


@pytest.mark.parametrize('syntax_char', '[{("\\,=)]}:')
def test_every_syntax_character_round_trips_inside_strings(syntax_char: str) -> None:
    values = [syntax_char, f'{syntax_char}value', f'value{syntax_char}', f'a{syntax_char}b']

    encoded = ENCODER.encode(values, {})

    assert DECODER.decode(encoded) == (values, {})


@pytest.mark.parametrize(
    ('positional', 'keyword', 'expected'),
    [
        ([], {}, '()'),
        ([1, 2], {}, '(1, 2)'),
        ([True, False, None], {}, '(true, false, null)'),
        ([], {'answer': 42}, '(answer = 42)'),
        ([1], {'answer': 42}, '(1, answer = 42)'),
        ([['plain', 2]], {'empty': []}, '([plain, 2], empty = [])'),
        ([{'key': 'value', '': None}], {}, '({key: value, "": null})'),
    ],
)
def test_encoder_produces_canonical_format(
    positional: list[Any], keyword: dict[str, Any], expected: str
) -> None:
    assert ENCODER.encode(positional, keyword) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('plain', 'plain'),
        ('two words', 'two words'),
        ('', '""'),
        (' leading', '" leading"'),
        ('trailing ', '"trailing "'),
        ('123', '"123"'),
        ('true', '"true"'),
        ('null', '"null"'),
        ('NaN', '"NaN"'),
        ('a,b', '"a,b"'),
        ('line\nbreak', 'line\nbreak'),
        ('back\\slash', '"back\\\\slash"'),
    ],
)
def test_string_encoding_is_unambiguous_and_minimal(value: str, expected: str) -> None:
    assert ENCODER.encode_string(value) == expected


@pytest.mark.parametrize('token', VALID_TOKENS)
def test_valid_token_characters_work_in_every_significant_position(token: str) -> None:
    call = Call(name=token, args=(), kwargs={})
    encoded = ENCODER.encode([], {token: 1})

    assert call.name == token
    assert DECODER.decode(encoded) == ([], {token: 1})


@pytest.mark.parametrize(
    'token', ['', '0', '9name', 'has-dash', 'has space', 'имя', 'name.', '$name']
)
def test_invalid_tokens_are_rejected_by_call_and_keyword_encoder(token: str) -> None:
    with pytest.raises(ValueError):
        Call(name=token, args=(), kwargs={})

    with pytest.raises(CallEncodeError):
        ENCODER.encode([], {token: 1})


def test_encoder_rejects_unsupported_value_type() -> None:
    with pytest.raises(TypeError, match='Unexpected value type'):
        ENCODER.encode_value(object())


def test_encoder_rejects_non_string_mapping_keys() -> None:
    value: dict[Any, Any] = {1: 'one'}

    with pytest.raises(ValueError, match='Mapping key must be a string'):
        ENCODER.encode_value(value)


@pytest.mark.parametrize(
    ('source', 'expected_positional', 'expected_keyword'),
    [
        ('()', [], {}),
        ('(   )', [], {}),
        ('(1, two words, true, null)', [1, 'two words', True, None], {}),
        ('(1, key=value)', [1], {'key': 'value'}),
        (
            '( first ,\n second\t, key \t= [true, {nested: null}] )',
            ['first', 'second'],
            {'key': [True, {'nested': None}]},
        ),
        ('({"": empty, 1: one, false: no})', [{'': 'empty', 1: 'one', False: 'no'}], {}),
        ('("\\u043f\\u0440\\u0438\\u0432\\u0435\\u0442")', ['привет'], {}),
    ],
)
def test_decoder_accepts_valid_handwritten_syntax(
    source: str, expected_positional: list[Any], expected_keyword: dict[str, Any]
) -> None:
    assert DECODER.decode(source) == (expected_positional, expected_keyword)


@pytest.mark.parametrize(
    ('source', 'position', 'message'),
    [
        ('', 0, 'Empty value passed'),
        ('value', 0, "must start with '('"),
        ('(', 1, "Expected args closure (')')"),
        ('(1', 2, 'Expected end of bare value'),
        ('(1) trailing', 3, 'Trailing data'),
        ('(,)', 1, 'Empty bare value'),
        ('(a=)', 3, 'Empty bare value'),
        ('(a=1, a=2)', 6, "Duplicate keyword argument 'a'"),
        ('(a=1, 2)', 6, 'Keyword name cannot start with a digit'),
        ('([1)', 3, 'Expected sequence item separator'),
        ('({a})', 3, 'Expected key-value separator'),
        ('({a: 1, a: 2})', 8, "Duplicate mapping key 'a'"),
        ('({[]: value})', 2, 'Expected non-container types only'),
        ('("bad\\q")', 5, 'Bad enquoted string'),
    ],
)
def test_decoder_reports_malformed_syntax_at_exact_position(
    source: str, position: int, message: str
) -> None:
    assert_args_decode_error(source, position, message)


@pytest.mark.parametrize(
    ('source', 'position'),
    [
        ('(a@b=1)', 2),
        ('(key@=1)', 4),
        ('(ключ=1)', 1),
    ],
)
def test_decoder_rejects_forbidden_keyword_characters(source: str, position: int) -> None:
    assert_args_decode_error(source, position, 'Forbidden char')


def test_args_raw_decode_starts_at_offset_and_leaves_trailing_text() -> None:
    source = 'prefix(1, key=two)suffix'

    positional, keyword, end = DECODER.raw_decode(source, len('prefix'))

    assert positional == [1]
    assert keyword == {'key': 'two'}
    assert source[end:] == 'suffix'


@pytest.mark.parametrize(('source', 'position'), [('', 0), ('text', 0), ('xx()', 0), ('xx()', 1)])
def test_args_raw_decode_without_opening_parenthesis_does_not_consume_input(
    source: str, position: int
) -> None:
    assert DECODER.raw_decode(source, position) == ([], {}, position)


def test_call_raw_decode_with_arguments_and_offset() -> None:
    source = 'prefix $notify(1, text=hello) suffix'
    start = source.index('$')

    call, end = CALL_DECODER.raw_decode(source, start)

    assert call is not None
    assert call.name == 'notify'
    assert list(call.args) == [1]
    assert call.kwargs == {'text': 'hello'}
    assert source[end:] == ' suffix'


def test_call_raw_decode_without_parentheses_stops_at_whitespace() -> None:
    source = '$notify trailing text'

    call, end = CALL_DECODER.raw_decode(source)

    assert call is not None
    assert call.name == 'notify'
    assert list(call.args) == []
    assert call.kwargs == {}
    assert source[end:] == ' trailing text'


@pytest.mark.parametrize(
    ('source', 'position'), [('', 0), ('plain', 0), ('x$call', 0), ('$', 0), ('$ call', 0)]
)
def test_call_raw_decode_without_call_does_not_consume_input(source: str, position: int) -> None:
    assert CALL_DECODER.raw_decode(source, position) == (None, position)


@pytest.mark.parametrize(
    ('source', 'position', 'message'),
    [
        ('$1call', 1, 'Call name cannot start with a digit'),
        ('$bad-name', 4, "contains not allowed char '-'"),
        ('$имя', 1, "contains not allowed char 'и'"),
    ],
)
def test_call_raw_decode_reports_invalid_name(source: str, position: int, message: str) -> None:
    with pytest.raises(CallDecodeError) as exc_info:
        CALL_DECODER.raw_decode(source)

    assert exc_info.value._pos == position
    assert message in str(exc_info.value)


def test_extract_calls_preserves_text_call_data_and_source_spans() -> None:
    call_source = '$notify(1, text=hello)'
    source = f'before {call_source} after'
    start = source.index(call_source)

    result = CALL_DECODER.extract_calls(source)

    assert result.string == source
    assert result.call_spans == {
        (start, start + len(call_source)): Call(name='notify', args=[1], kwargs={'text': 'hello'})
    }
    assert result.decoded[0] == 'before '
    call = result.decoded[1]
    assert isinstance(call, Call)
    assert call.name == 'notify'
    assert list(call.args) == [1]
    assert call.kwargs == {'text': 'hello'}
    assert result.decoded[2] == ' after'


def test_extract_calls_supports_adjacent_calls() -> None:
    source = '$first()$second(2)'

    result = CALL_DECODER.extract_calls(source)

    assert result.call_spans == {
        (0, len('$first()')): Call(name='first', args=[], kwargs={}),
        (len('$first()'), len(source)): Call(name='second', args=[2], kwargs={}),
    }
    assert len(result.decoded) == 2
    first, second = result.decoded
    assert isinstance(first, Call)
    assert isinstance(second, Call)
    assert (first.name, list(first.args), first.kwargs) == ('first', [], {})
    assert (second.name, list(second.args), second.kwargs) == ('second', [2], {})


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('', []),
        ('plain text', ['plain text']),
        ('$', ['$']),
        ('price $$5', ['price $5']),
        ('$$$$', ['$$']),
    ],
)
def test_extract_calls_treats_double_dollar_as_an_escape(source: str, expected: list[str]) -> None:
    result = CALL_DECODER.extract_calls(source)

    assert result.string == source
    assert result.decoded == expected
    assert result.call_spans == {}
