from __future__ import annotations

from dataclasses import dataclass

import pytest

from hubplatform.core import PydanticSerializableMixin
from hubplatform.exceptions.telegram import BadCallbackIdentifierError
from hubplatform.telegram.callback_data import (
    CallbackData,
    validate_identifier,
    is_keyword_callback_data,
    is_positional_callback_data,
)


class EmptyCallbackData(CallbackData, identifier='empty'): ...


class CallbackDataWithFields(CallbackData, identifier='f'):
    integer: int
    floating: float
    text: str
    boolean: bool
    items: list[int | str | bool]
    mapping: dict[str, int | str | bool]


@dataclass(frozen=True)
class SerializableValue(PydanticSerializableMixin):
    value: str

    def __pydantic_serialize__(self) -> str:
        return self.value

    @classmethod
    def __pydantic_deserialize__(cls, value: str) -> SerializableValue:
        return cls(value)


class CallbackDataWithSerializableValue(CallbackData, identifier='m'):
    value: SerializableValue


def test_validate_identifier_rejects_empty_identifier() -> None:
    with pytest.raises(
        BadCallbackIdentifierError,
        match=r'^Callback identifier cannot be empty\.$',
    ):
        validate_identifier('')


def test_validate_identifier_rejects_unsupported_symbols() -> None:
    with pytest.raises(
        BadCallbackIdentifierError,
        match=r"^Callback identifier contains invalid symbols: ':'\.$",
    ):
        validate_identifier('invalid:identifier')


def test_validate_identifier_returns_valid_identifier() -> None:
    identifier = 'Select.item_42-test'

    assert validate_identifier(identifier) == identifier


@pytest.mark.parametrize(
    ['callback_data', 'is_positional'],
    [
        ('positional_callback_data', True),
        ('!keyword_callback_data', False),
    ],
)
def test_format_recognition(callback_data: str, is_positional: bool) -> None:
    is_positional_r = is_positional_callback_data(callback_data)
    is_keyword_r = is_keyword_callback_data(callback_data)

    assert is_positional_r is is_positional
    assert is_keyword_r is not is_positional


def test_pack_and_unpack_positional_callback_without_fields() -> None:
    callback = EmptyCallbackData()

    packed = callback.pack_compact()

    assert packed == 'empty'
    assert EmptyCallbackData.unpack(packed) == callback


def test_pack_and_unpack_positional_callback_with_fields() -> None:
    callback = CallbackDataWithFields(
        integer=1,
        floating=2.5,
        text='x,y%',
        boolean=True,
        items=[1, 'x', False],
        mapping={'n': 1, 's': 'x', 'b': True},
    )

    packed = callback.pack_compact()

    assert packed == 'f,1,2.5,"x,y%",1,[1,x,0],{n:1,s:x,b:1}'
    assert CallbackDataWithFields.unpack(packed) == callback


def test_pack_and_unpack_positional_callback_with_serializable_value() -> None:
    callback = CallbackDataWithSerializableValue(value=SerializableValue('x,y%'))

    packed = callback.pack_compact()

    assert packed == 'm,"x,y%"'
    assert CallbackDataWithSerializableValue.unpack(packed) == callback


def test_pack_and_unpack_keyword_callback_without_fields() -> None:
    callback = EmptyCallbackData()

    packed = callback.pack()

    assert packed == '!empty[{},{}]'
    assert EmptyCallbackData.unpack(packed) == callback


def test_pack_and_unpack_keyword_callback_with_fields() -> None:
    callback = CallbackDataWithFields(
        integer=1,
        floating=2.5,
        text='x,y%',
        boolean=True,
        items=[1, 'x', False],
        mapping={'n': 1, 's': 'x', 'b': True},
    )

    packed = callback.pack()

    assert packed == (
        '!f[{integer:1,floating:2.5,text:"x,y%",boolean:1,items:[1,x,0],mapping:{n:1,s:x,b:1}},{}]'
    )
    assert CallbackDataWithFields.unpack(packed) == callback


def test_pack_and_unpack_keyword_callback_with_serializable_value() -> None:
    callback = CallbackDataWithSerializableValue(value=SerializableValue('x,y%'))

    packed = callback.pack()

    assert packed == '!m[{value:"x,y%"},{}]'
    assert CallbackDataWithSerializableValue.unpack(packed) == callback
