"""Models and serialization helpers for Telegram callback data."""

from __future__ import annotations


__all__ = [
    'CallbackData',
    'ParsedEnvelope',
    'PositionalCallbackEnvelope',
    'KeywordCallbackEnvelope',
    'CallbackEnvelope',
]

import json
import string
from typing import TYPE_CHECKING, Any, Self, ClassVar, Annotated
from abc import ABC, abstractmethod

from pydantic import Field, BaseModel, AfterValidator
from aiogram.types import CallbackQuery

from hubplatform.exceptions.telegram import (
    CallbackDataPackError,
    NotPositionalDataError,
    IdentifierMismatchError,
    CallbackDataParsingError,
    NotSerializableValueError,
    PositionalCallbackWithContextError,
)
from hubplatform.telegram.callback_data import global_hash_service
from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer


if TYPE_CHECKING:
    from hubplatform.telegram.callback_data.hash import HashService

    from .filter import CallbackQueryFilter


_ALLOWED_IDENTIFIER_SYMBOLS = frozenset(string.ascii_letters + string.digits + '._-')


def validate_identifier(identifier: str) -> str:
    """
    Validate a callback identifier.

    Identifier must match following regular expression: `[a-zA-Z0-9\\._-]`

    :param identifier: Identifier to validate.
    :return: The validated identifier unchanged.
    :raises ValueError: If the identifier is empty or contains unsupported symbols.
    """
    if not identifier:
        raise ValueError('Callback identifier cannot be empty.')
    invalid_symbols = set(identifier) - _ALLOWED_IDENTIFIER_SYMBOLS
    if invalid_symbols:
        symbols = ''.join(sorted(invalid_symbols))
        raise ValueError(f'Callback identifier contains invalid symbols: {symbols!r}.')
    return identifier


def _hash_service(hash_service: HashService | None) -> HashService:
    """Return an explicitly supplied hash service or the global default."""
    return hash_service if hash_service is not None else global_hash_service()


def parse_callback_data(data: str | CallbackQuery):
    """
    Parse a callback data string or an aiogram `CallbackQuery`.
    A parsed envelope cached on an aiogram `CallbackQuery` is reused when available.

    :param data: Packed callback data or an aiogram `CallbackQuery` containing it.
    :return: The parsed keyword or positional envelope.
    :raises CallbackDataParsingError: If the callback data cannot be parsed.
    """
    if isinstance(data, CallbackQuery):
        parsed = getattr(data, '_hubplatform_parsed_data_envelope', None)
        if isinstance(parsed, ParsedEnvelope):
            return parsed

        data_str = data.data
    else:
        data_str = data

    if data_str is None:
        raise CallbackDataParsingError('Passed aiogram `CallbackQuery` does not contain `data`.')

    if PositionalCallbackEnvelope.is_positional_callback(data_str):
        envelope = PositionalCallbackEnvelope._unpack(data_str)
    else:
        envelope = KeywordCallbackEnvelope._unpack(data_str)


class CallbackEnvelope(BaseModel, ABC):
    """Base transport representation of callback data.

    :param identifier: Identifier used to route the callback to its payload model.
    """

    identifier: Annotated[str, AfterValidator(validate_identifier)]

    @abstractmethod
    def _pack(self) -> str:
        """Serialize the envelope using its concrete wire format."""
        ...

    @classmethod
    @abstractmethod
    def _unpack(cls, data: str) -> CallbackEnvelope:
        """Deserialize an envelope from its concrete wire format."""
        ...

    def pack(self) -> str:
        """Serialize the envelope to a callback-data string.

        :return: Packed callback data.
        :raises CallbackDataPackError: If serialization fails.
        """
        try:
            return self._pack()
        except CallbackDataPackError:
            raise
        except Exception as e:
            raise CallbackDataPackError(f'An unexpected error occurred during packing: {e}') from e

    @classmethod
    def unpack(cls, data: str) -> CallbackEnvelope:
        """Deserialize a callback-data string into an envelope.

        :param data: Packed callback data.
        :return: The parsed envelope.
        :raises CallbackDataParsingError: If parsing fails.
        """
        try:
            return cls._unpack(data)
        except CallbackDataParsingError:
            raise
        except Exception as e:
            raise CallbackDataParsingError('An unexpected error occurred during parsing.') from e


class KeywordCallbackEnvelope(CallbackEnvelope):
    """Envelope that stores named payload fields and context as JSON.

    :param identifier: Identifier used to route the callback.
    :param fields: Payload values keyed by model field name.
    :param context: Additional data carried alongside the payload.
    """

    fields: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    def _pack(self) -> str:
        """Serialize the identifier, fields, and context in keyword format."""
        data = self.model_dump(mode='json', fallback=pydantic_fallback_serializer)

        data_str = json.dumps(
            [data['fields'], data['context']],
            ensure_ascii=False,
            separators=(',', ':'),
        )

        return self.identifier + data_str

    @classmethod
    def _unpack(cls, data: str) -> KeywordCallbackEnvelope:
        """Deserialize keyword-formatted callback data.

        :param data: Callback data containing an identifier followed by a JSON array.
        :return: The parsed keyword envelope.
        """
        identifier, sep, data = data.partition('[')
        fields, context = json.loads(sep + data)
        return KeywordCallbackEnvelope(identifier=identifier, fields=fields, context=context)


class PositionalCallbackEnvelope(CallbackEnvelope):
    """Compact envelope that stores payload values by position.

    Positional callback data uses the ``!identifier:value:...`` format. Colons and
    percent signs inside string values are escaped.

    :param identifier: Identifier used to route the callback.
    :param fields: Payload values in concrete-model field order.
    """

    fields: list[Any] = Field(default_factory=list)

    def _pack(self) -> str:
        """Serialize the identifier and field values in positional format."""
        fields = self.model_dump(mode='json')['fields']
        result = f'!{self.identifier}'
        if fields:
            result += ':' + ':'.join(self._serialize_value(i) for i in fields)
        return result

    @classmethod
    def _unpack(cls, data: str) -> PositionalCallbackEnvelope:
        """Deserialize positional callback data.

        :param data: Callback data in ``!identifier:value:...`` format.
        :return: The parsed positional envelope.
        :raises NotPositionalDataError: If ``query`` is not positional callback data.
        """
        if not cls.is_positional_callback(data):
            raise NotPositionalDataError()

        identifier, sep, fields = data[1:].partition(':')
        if sep:
            positional = [i.replace('%S', ':').replace('%P', '%') for i in fields.split(':')]
        else:
            positional = []
        return PositionalCallbackEnvelope(identifier=identifier, fields=positional)

    def _serialize_value(self, value: Any) -> str:
        """Serialize one value for a positional envelope.

        :param value: Boolean, integer, float, or string value to serialize.
        :return: The value encoded as a positional field.
        :raises NotSerializableValueError: If the value type is unsupported.
        """
        if type(value) is bool:
            return str(int(value))
        if type(value) in (int, float):
            return str(value)
        if type(value) is str:
            return value.replace('%', '%P').replace(':', '%S')
        raise NotSerializableValueError(f'Value {value!r} is not serializable.')

    @staticmethod
    def is_positional_callback(data: str) -> bool:
        """Check whether a string can represent positional callback data.

        :param data: Callback-data string to inspect.
        :return: Whether the string has the positional prefix and valid Telegram length.
        """
        return data.startswith('!') and len(data) <= 64


ParsedEnvelope = KeywordCallbackEnvelope | PositionalCallbackEnvelope


class CallbackData(BaseModel):
    """Base model for concrete, typed callback payloads.

    Each subclass must declare a non-empty identifier in its class definition, for
    example ``class SelectItem(CallbackData, identifier='select_item')``. Fields added
    by the subclass form the callback payload; ``context`` is auxiliary data available
    only in keyword envelopes.

    :param context: Additional data carried alongside the callback payload.
    """

    identifier: ClassVar[str] = ''
    context: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        """Validate the class-level identifier after Pydantic initialization."""
        validate_identifier(self.identifier)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Configure and validate the identifier declared by a subclass.

        :param kwargs: Subclass options, including the required ``identifier``.
        :raises ValueError: If ``identifier`` is empty or contains unsupported symbols.
        :raises TypeError: If ``identifier`` is not a string.
        """
        identifier = kwargs.pop('identifier', None)
        if not identifier:
            raise ValueError(
                f'Not empty identifier required. Example: '
                f"`class {cls.__name__}(CallbackData, identifier='my_callback'): ...`",
            )
        if not isinstance(identifier, str):
            raise TypeError('Callback identifier must be a string.')

        cls.identifier = validate_identifier(identifier)
        super().__init_subclass__(**kwargs)

    def _dump_callback_fields(self) -> dict[str, Any]:
        """Dump concrete payload fields in JSON-compatible form.

        Fields defined by :class:`CallbackData`, such as ``context``, are excluded.

        :return: Serialized payload fields in model declaration order.
        """
        return self.model_dump(
            mode='json',
            exclude=set(CallbackData.model_fields.keys()),
            fallback=pydantic_fallback_serializer,
        )

    def to_keyword_envelope(self) -> KeywordCallbackEnvelope:
        """Convert the payload to a keyword envelope, preserving its context.

        :return: An envelope containing named payload fields and context.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        try:
            return KeywordCallbackEnvelope(
                identifier=self.identifier,
                fields=self._dump_callback_fields(),
                context=self.context,
            )
        except Exception as e:
            raise CallbackDataPackError(
                f'An unexpected error occurred while packing {self.__class__.__name__} '
                f'to keyword envelope: {e}'
            ) from e

    def to_positional_envelope(self, *, drop_context: bool = False) -> PositionalCallbackEnvelope:
        """Convert the payload to a compact positional envelope.

        :param drop_context: Discard non-empty context. Positional envelopes cannot
            carry context.
        :return: An envelope containing payload values in model field order.
        :raises PositionalCallbackWithContextError: If context is present and
            ``drop_context`` is false.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        if self.context and not drop_context:
            raise PositionalCallbackWithContextError(
                'Packing to positional query with non-empty context is not allowed. '
                'Pass `drop_context=True` to not include context in packed query.'
            )

        try:
            return PositionalCallbackEnvelope(
                identifier=self.identifier, fields=list(self._dump_callback_fields().values())
            )
        except Exception as e:
            raise CallbackDataPackError(
                f'An unexpected error occurred while packing {self.__class__.__name__} '
                f'to positional envelope: {e}'
            ) from e

    @classmethod
    def from_envelope(cls, envelope: ParsedEnvelope) -> Self:
        """Validate an envelope as an instance of this callback model.

        Keyword fields are matched by name; positional fields are matched in model
        declaration order.

        :param envelope: Parsed envelope to validate.
        :return: A validated instance of the concrete callback model.
        :raises IdentifierMismatchError: If the envelope targets another model.
        :raises CallbackDataParsingError: If the payload cannot be validated.
        """
        if envelope.identifier != cls.identifier:
            raise IdentifierMismatchError(
                f'Identifier from envelope ({envelope.identifier!r}) does not match with '
                f'CallbackData identifier ({cls.identifier!r}).)'
            )

        try:
            if isinstance(envelope, KeywordCallbackEnvelope):
                return cls.model_validate(envelope.fields | {'context': envelope.context})

            base_field_names = set(CallbackData.model_fields.keys())
            field_names = [k for k in cls.model_fields.keys() if k not in base_field_names]
            return cls.model_validate(dict(zip(field_names, envelope.fields, strict=True)))
        except Exception as e:
            raise CallbackDataParsingError(
                f'An unexpected error occurred while unpacking '
                f'{cls.__name__!r} from envelope: {e}.'
            ) from e

    def pack(self) -> str:
        """Serialize the payload in keyword format, preserving context.

        :return: Packed callback data.
        :raises CallbackDataPackError: If serialization fails.
        """
        return self.to_keyword_envelope().pack()

    def pack_compact(self, *, drop_context: bool = False) -> str:
        """Serialize the payload in compact positional format.

        :param drop_context: Discard non-empty context before serialization.
        :return: Packed positional callback data.
        :raises PositionalCallbackWithContextError: If context is present and
            ``drop_context`` is false.
        :raises CallbackDataPackError: If serialization fails.
        """
        return self.to_positional_envelope(drop_context=drop_context).pack()

    @classmethod
    def unpack(cls, data: str | ParsedEnvelope) -> Self:
        """Parse callback data and validate it as this callback model.

        :param data: Packed callback data or an already parsed envelope.
        :return: A validated instance of the concrete callback model.
        :raises IdentifierMismatchError: If the callback targets another model.
        :raises CallbackDataParsingError: If parsing or validation fails.
        """
        if isinstance(data, str):
            if PositionalCallbackEnvelope.is_positional_callback(data):
                data = PositionalCallbackEnvelope._unpack(data)
            else:
                data = KeywordCallbackEnvelope._unpack(data)

        return cls.from_envelope(data)

    @classmethod
    def filter(cls) -> CallbackQueryFilter:
        """
        Create an aiogram filter for this callback model.

        :return: A filter that parses and validates matching callback queries.
        """
        from .filter import CallbackQueryFilter

        return CallbackQueryFilter(callback_data=cls)
