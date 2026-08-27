from __future__ import annotations


__all__ = [
    'CallbackData',
    'CallbackDataEnvelope',
    'PositionalCallbackDataEnvelope',
    'KeywordCallbackDataEnvelope',
    '_CallbackDataEnvelope',
    'parse_callback_data',
    'validate_identifier',
    'is_keyword_callback_data',
    'is_positional_callback_data',
    'global_compression_codecs_registry',
]

import string
from typing import TYPE_CHECKING, Any, Self, ClassVar, Annotated
from abc import ABC, abstractmethod

from pydantic import Field, BaseModel, AfterValidator
from aiogram.types import CallbackQuery
from aiogram.utils.magic_filter import MagicFilter

from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer
from hubplatform.exceptions.telegram.callback_data import (
    CallbackDataPackError,
    CallbackDataUnpackError,
    NotSerializableValueError,
    BadCallbackIdentifierError,
    InvalidCallbackDataFormatError,
    CallbackIdentifierMismatchError,
)

from .compress import CompressionCodecsRegistry, ZLibBase85CompressionCodec
from .compact_encoder import dumps_compact, loads_compact


if TYPE_CHECKING:
    from .filter import CallbackQueryFilter


_ALLOWED_IDENTIFIER_SYMBOLS = frozenset(string.ascii_lowercase + '_.')
_GLOBAL_COMPRESSION_CODECS_REGISTRY = CompressionCodecsRegistry(
    reserved_codec=ZLibBase85CompressionCodec(version='0', compression_dict=b'')
)


def global_compression_codecs_registry() -> CompressionCodecsRegistry:
    return _GLOBAL_COMPRESSION_CODECS_REGISTRY


def validate_identifier(identifier: str) -> str:
    """Validate a callback identifier.

    Identifier must match following regular expression: `[a-zA-Z0-9\\._-]`

    :param identifier: Identifier to validate.
    :return: The validated identifier unchanged.
    :raises ValueError: If the identifier is empty or contains unsupported symbols.
    """
    if not identifier:
        raise BadCallbackIdentifierError('Callback identifier cannot be empty.')
    invalid_symbols = set(identifier) - _ALLOWED_IDENTIFIER_SYMBOLS
    if invalid_symbols:
        symbols = ''.join(sorted(invalid_symbols))
        raise BadCallbackIdentifierError(
            f'Callback identifier contains invalid symbols: {symbols!r}.'
        )
    return identifier


class _CallbackDataEnvelope(BaseModel, ABC):
    """Base transport representation of callback data.

    :param identifier: CallbackData identifier.
    """

    identifier: Annotated[str, AfterValidator(validate_identifier)]

    @abstractmethod
    def _pack(
        self,
        compress: bool,
        compression_version: str | None,
        fallback_reserved: bool,
    ) -> str:
        """Serialize the envelope using its concrete wire format."""
        ...

    @classmethod
    @abstractmethod
    def _unpack(cls, data: str) -> Self:
        """Deserialize an envelope from its concrete wire format."""
        ...

    def pack(
        self,
        compress: bool = True,
        *,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
    ) -> str:
        """Serialize the envelope to a callback-data string.

        :return: Packed callback data.
        :raises CallbackDataPackError: If serialization fails.
        """
        try:
            return self._pack(
                compress=compress,
                compression_version=compression_version,
                fallback_reserved=fallback_reserved,
            )
        except CallbackDataPackError:
            raise
        except Exception as e:
            raise CallbackDataPackError(f'An unexpected error occurred during packing: {e}') from e

    @classmethod
    def unpack(cls, data: str) -> Self:
        """Deserialize a callback-data string into an envelope.

        :param data: Packed callback data.
        :return: The parsed envelope.
        :raises CallbackDataUnpackError: If unpacking fails.
        """
        try:
            return cls._unpack(data)
        except CallbackDataUnpackError:
            raise
        except Exception as e:
            raise CallbackDataUnpackError('An unexpected error occurred during unpacking.') from e


class KeywordCallbackDataEnvelope(_CallbackDataEnvelope):
    """Envelope that stores named payload fields and context."""

    fields: dict[str, Any] = Field(default_factory=dict)

    def _pack(
        self,
        compress: bool,
        compression_version: str | None,
        fallback_reserved: bool,
    ) -> str:
        data = self.model_dump(mode='json', fallback=pydantic_fallback_serializer)
        data_str = dumps_compact(data['fields'], root=False)
        result = '!' + self.identifier + data_str
        if not compress:
            return result

        result_bytes = result.encode('utf-8')
        if len(result_bytes) < 64:
            return result

        return _GLOBAL_COMPRESSION_CODECS_REGISTRY.compress(
            result_bytes,
            version=compression_version,
            fallback_reserved=fallback_reserved,
        ).decode('utf-8')

    @classmethod
    def _unpack(cls, data: str) -> KeywordCallbackDataEnvelope:
        if not is_keyword_callback_data(data):
            raise InvalidCallbackDataFormatError('Not a keyword callback data format.')

        data = _GLOBAL_COMPRESSION_CODECS_REGISTRY.decompress(data)

        identifier, sep, data = data.partition('{')
        fields = loads_compact(sep + data)
        return KeywordCallbackDataEnvelope(identifier=identifier[1:], fields=fields)


class PositionalCallbackDataEnvelope(_CallbackDataEnvelope):
    """Compact envelope that stores payload values by position.

    Positional callback data uses the ``!identifier:value:...`` format. Colons and
    percent signs inside string values are escaped.
    """

    fields: list[Any] = Field(default_factory=list)

    def _pack(
        self,
        compress: bool,
        compression_version: str | None,
        fallback_reserved: bool,
    ) -> str:
        fields = self.model_dump(mode='json')['fields']
        result = self.identifier
        if fields:
            fields_str = dumps_compact(fields)
            result += fields_str

        if not compress:
            return result

        result_bytes = result.encode('utf-8')
        if len(result_bytes) < 64:
            return result

        return _GLOBAL_COMPRESSION_CODECS_REGISTRY.compress(
            result_bytes,
            version=compression_version,
            fallback_reserved=fallback_reserved,
        ).decode('utf-8')

    @classmethod
    def _unpack(cls, data: str) -> PositionalCallbackDataEnvelope:
        if not is_positional_callback_data(data):
            raise InvalidCallbackDataFormatError('Not a positional callback data format.')

        data = _GLOBAL_COMPRESSION_CODECS_REGISTRY.decompress(data)

        identifier, sep, fields = data.partition(',')
        return PositionalCallbackDataEnvelope(
            identifier=identifier, fields=loads_compact(sep + fields) or []
        )

    def _serialize_value(self, value: Any) -> str:
        try:
            return dumps_compact(value)
        except Exception as e:
            raise NotSerializableValueError(f'Value {value!r} is not serializable.') from e


CallbackDataEnvelope = KeywordCallbackDataEnvelope | PositionalCallbackDataEnvelope


def is_positional_callback_data(data: str) -> bool:
    """Check whether a string can represent positional callback data.

    :param data: Callback-data string to inspect.
    :return: Whether the string has the positional prefix and valid Telegram length.
    """
    return not data.startswith('!')


def is_keyword_callback_data(data: str) -> bool:
    """Check whether a string can represent keyword callback data.

    :param data: Callback-data string to inspect.
    :return: Whether the string has the positional prefix and valid Telegram length.
    """
    return not is_positional_callback_data(data)


def parse_callback_data(data: str | CallbackQuery | CallbackDataEnvelope) -> CallbackDataEnvelope:
    """Parse a callback data string or an aiogram `CallbackQuery`.
    A parsed envelope cached on an aiogram `CallbackQuery` is reused when available.

    :param data: Packed callback data or an aiogram `CallbackQuery` containing it.
        For API convenience, `KeywordCallbackDataEnvelope` and `PositionalCallbackDataEnvelope`
        instances are also accepted and fast-returned unchanged.

    :return: The parsed keyword or positional envelope.
    :raises CallbackDataUnpackError: If the callback data cannot be parsed.
    """
    if isinstance(data, CallbackDataEnvelope):
        return data

    if isinstance(data, CallbackQuery):
        parsed = getattr(data, '_hubplatform_parsed_callback_envelope', None)
        if isinstance(parsed, CallbackDataEnvelope):
            return parsed

        data_str = data.data
    else:
        data_str = data

    if not data_str:
        raise CallbackDataUnpackError('Callback data string is empty.')

    data_str = _GLOBAL_COMPRESSION_CODECS_REGISTRY.decompress(data_str)

    envelope: CallbackDataEnvelope
    if is_positional_callback_data(data_str):
        envelope = PositionalCallbackDataEnvelope.unpack(data_str)
    else:
        envelope = KeywordCallbackDataEnvelope.unpack(data_str)

    if isinstance(data, CallbackQuery):
        setattr(data, '_hubplatform_parsed_callback_envelope', envelope)
    return envelope


class CallbackData(BaseModel):
    """Base model for concrete, typed callback payloads.

    Each subclass must declare a non-empty identifier in its class definition, for
    example ``class SelectItem(CallbackData, identifier='select_item')``. Fields added
    by the subclass form the callback payload.

    """

    identifier: ClassVar[str] = ''

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

        Fields defined by :class:`CallbackData`, are excluded.

        :return: Serialized payload fields in model declaration order.
        """
        return self.model_dump(
            mode='json',
            exclude=set(CallbackData.model_fields.keys()),
            fallback=pydantic_fallback_serializer,
        )

    def to_keyword_envelope(self) -> KeywordCallbackDataEnvelope:
        """Convert the payload to a keyword envelope.

        :return: An envelope containing named payload fields.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        try:
            return KeywordCallbackDataEnvelope(
                identifier=self.identifier,
                fields=self._dump_callback_fields(),
            )
        except Exception as e:
            raise CallbackDataPackError(
                f'An unexpected error occurred while packing {self.__class__.__name__} '
                f'to keyword envelope: {e}'
            ) from e

    def to_positional_envelope(self) -> PositionalCallbackDataEnvelope:
        """Convert the payload to a compact positional envelope.

        :return: An envelope containing payload values in model field order.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        try:
            return PositionalCallbackDataEnvelope(
                identifier=self.identifier, fields=list(self._dump_callback_fields().values())
            )
        except Exception as e:
            raise CallbackDataPackError(
                f'An unexpected error occurred while packing {self.__class__.__name__} '
                f'to positional envelope: {e}'
            ) from e

    @classmethod
    def from_envelope(cls, envelope: CallbackDataEnvelope) -> Self:
        """Validate an envelope as an instance of this callback model.

        Keyword fields are matched by name; positional fields are matched in model
        declaration order.

        :param envelope: Parsed envelope to validate.
        :return: A validated instance of the concrete callback model.
        :raises CallbackIdentifierMismatchError: If the envelope targets another model.
        :raises CallbackDataUnpackError: If the payload cannot be validated.
        """
        if envelope.identifier != cls.identifier:
            raise CallbackIdentifierMismatchError(
                f'Identifier from envelope ({envelope.identifier!r}) does not match with '
                f'CallbackData identifier ({cls.identifier!r}).)'
            )

        try:
            if isinstance(envelope, KeywordCallbackDataEnvelope):
                return cls.model_validate(envelope.fields)

            base_field_names = set(CallbackData.model_fields.keys())
            field_names = [k for k in cls.model_fields.keys() if k not in base_field_names]
            return cls.model_validate(dict(zip(field_names, envelope.fields, strict=True)))
        except Exception as e:
            raise CallbackDataUnpackError(
                f'An unexpected error occurred while unpacking '
                f'{cls.__name__!r} from envelope: {e}.'
            ) from e

    def pack(
        self,
        *,
        compress: bool = True,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
    ) -> str:
        """Serialize the payload in keyword format.

        :return: Packed callback data.
        :raises CallbackDataPackError: If serialization fails.
        """
        return self.to_keyword_envelope().pack(
            compress=compress,
            compression_version=compression_version,
            fallback_reserved=fallback_reserved,
        )

    def pack_compact(
        self,
        *,
        compress: bool = True,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
    ) -> str:
        """Serialize the payload in compact positional format.

        :return: Packed positional callback data.
        :raises CallbackDataPackError: If serialization fails.
        """
        return self.to_positional_envelope().pack(
            compress=compress,
            compression_version=compression_version,
            fallback_reserved=fallback_reserved,
        )

    @classmethod
    def unpack(cls, data: str | CallbackDataEnvelope | CallbackQuery) -> Self:
        """Parse callback data and validate it as this callback model.

        :param data: Packed callback data or an already parsed envelope.
        :return: A validated instance of the concrete callback model.
        :raises CallbackIdentifierMismatchError: If the callback targets another model.
        :raises CallbackDataUnpackError: If unpacking or validation fails.
        """
        return cls.from_envelope(parse_callback_data(data))

    @classmethod
    def filter(cls, rule: MagicFilter | None = None) -> CallbackQueryFilter:
        """Create an aiogram filter for this callback model.

        :return: A filter that parses and validates matching callback queries.
        """
        from .filter import CallbackQueryFilter

        return CallbackQueryFilter(callback_data=cls, rule=rule)
