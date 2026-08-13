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
]

import zlib
import base64
import string
from typing import TYPE_CHECKING, Any, Self, Final, ClassVar, Annotated
from abc import ABC, abstractmethod

from pydantic import Field, BaseModel, AfterValidator
from aiogram.types import CallbackQuery

from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer
from hubplatform.exceptions.telegram.callback_data import (
    CallbackDataPackError,
    CallbackDataUnpackError,
    NotSerializableValueError,
    BadCallbackIdentifierError,
    InvalidCallbackDataFormatError,
    CallbackIdentifierMismatchError,
    PositionalContextNotSupportedError,
)

from .compact_encoder import dumps_compact, loads_compact


if TYPE_CHECKING:
    from .filter import CallbackQueryFilter


_ALLOWED_IDENTIFIER_SYMBOLS = frozenset(string.ascii_lowercase + '_.')
_VERSIONS: Final[frozenset[str]] = frozenset('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
_RESERVED_VERSION: Final[str] = '0'
_DEFAULT_DICT_VERSION: str = _RESERVED_VERSION
_COMPRESSION_DICTS: dict[str, bytes] = {
    '0': b'',
}
_COMPRESSION_CFG_LOCKED: bool = False


def _check_version(version: str, check_reserved: bool = False) -> None:
    if check_reserved and version == _RESERVED_VERSION:
        raise ValueError(f'Version {version!r} is reserved.')
    if version not in _VERSIONS:
        raise ValueError('Not a valid version. Valid version is a single character 1-9A-Z.')


def set_compression_dict(value: bytes, version: str) -> None:
    global _COMPRESSION_DICTS
    global _COMPRESSION_CFG_LOCKED

    if _COMPRESSION_CFG_LOCKED:
        raise RuntimeError('Compression configuration locked.')

    if not isinstance(value, bytes):
        raise ValueError('Compression dict must be a bytes.')

    if len(value) > 32768:
        raise ValueError(f'Compression dict is too large: {len(value)} > 32768.')

    _check_version(version, check_reserved=True)
    _COMPRESSION_DICTS[version] = value


def lock_compression_cfg() -> None:
    global _COMPRESSION_CFG_LOCKED
    _COMPRESSION_CFG_LOCKED = True


def get_compression_dict(version: str, fallback_reserved: bool = False) -> bytes:
    _check_version(version)
    if version not in _COMPRESSION_DICTS:
        if fallback_reserved:
            return _COMPRESSION_DICTS[_RESERVED_VERSION]
        raise KeyError(f'Compression dict with version {version} not found.')
    return _COMPRESSION_DICTS[version]


def set_default_compression_version(version: str) -> None:
    global _DEFAULT_DICT_VERSION
    if _COMPRESSION_CFG_LOCKED:
        raise RuntimeError('Compression configuration locked.')

    _check_version(version)
    _DEFAULT_DICT_VERSION = version


def compress_bytes(
    data: bytes, compression_version: str | None = None, fallback_reserved: bool = True
) -> bytes:
    version = _DEFAULT_DICT_VERSION if compression_version is None else compression_version
    _check_version(version)
    compression_dict = get_compression_dict(version, fallback_reserved=fallback_reserved)

    compressor = zlib.compressobj(
        level=9,
        wbits=-15,
        zdict=compression_dict,
    )
    result = compressor.compress(data) + compressor.flush()

    return version.encode('utf-8') + base64.b85encode(result)


def decompress(data: str) -> str:
    if not data:
        return ''

    version, payload = data[0], data[1:]
    if version not in _VERSIONS:
        return data

    decoded = base64.b85decode(payload)
    return (
        zlib.decompressobj(
            wbits=-15,
            zdict=get_compression_dict(version, fallback_reserved=False),
        )
        .decompress(decoded)
        .decode('utf-8')
    )


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
        compress: bool = True,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
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
    context: dict[str, Any] = Field(default_factory=dict)

    def _pack(
        self,
        compress: bool = True,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
    ) -> str:
        data = self.model_dump(mode='json', fallback=pydantic_fallback_serializer)
        data_str = dumps_compact([data['fields'], data['context']], root=False)
        result = '!' + self.identifier + data_str
        if not compress:
            return result

        result_bytes = result.encode('utf-8')
        if len(result_bytes) < 64:
            return result

        return compress_bytes(
            result_bytes,
            compression_version=compression_version,
            fallback_reserved=fallback_reserved,
        ).decode('utf-8')

    @classmethod
    def _unpack(cls, data: str) -> KeywordCallbackDataEnvelope:
        if not is_keyword_callback_data(data):
            raise InvalidCallbackDataFormatError('Not a keyword callback data format.')

        data = decompress(data)

        identifier, sep, data = data.partition('[')
        fields, context = loads_compact(sep + data)
        return KeywordCallbackDataEnvelope(
            identifier=identifier[1:], fields=fields, context=context
        )


class PositionalCallbackDataEnvelope(_CallbackDataEnvelope):
    """Compact envelope that stores payload values by position.

    Positional callback data uses the ``!identifier:value:...`` format. Colons and
    percent signs inside string values are escaped.
    """

    fields: list[Any] = Field(default_factory=list)

    def _pack(
        self,
        compress: bool = True,
        compression_version: str | None = None,
        fallback_reserved: bool = True,
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

        return compress_bytes(
            result_bytes,
            compression_version=compression_version,
            fallback_reserved=fallback_reserved,
        ).decode('utf-8')

    @classmethod
    def _unpack(cls, data: str) -> PositionalCallbackDataEnvelope:
        if not is_positional_callback_data(data):
            raise InvalidCallbackDataFormatError('Not a positional callback data format.')

        data = decompress(data)

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

    data_str = decompress(data_str)

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

    def to_keyword_envelope(self) -> KeywordCallbackDataEnvelope:
        """Convert the payload to a keyword envelope, preserving its context.

        :return: An envelope containing named payload fields and context.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        try:
            return KeywordCallbackDataEnvelope(
                identifier=self.identifier,
                fields=self._dump_callback_fields(),
                context=self.context,
            )
        except Exception as e:
            raise CallbackDataPackError(
                f'An unexpected error occurred while packing {self.__class__.__name__} '
                f'to keyword envelope: {e}'
            ) from e

    def to_positional_envelope(
        self, *, drop_context: bool = False
    ) -> PositionalCallbackDataEnvelope:
        """Convert the payload to a compact positional envelope.

        :param drop_context: Discard non-empty context. Positional envelopes cannot
            carry context.
        :return: An envelope containing payload values in model field order.
        :raises PositionalContextNotSupportedError: If context is present and
            ``drop_context`` is false.
        :raises CallbackDataPackError: If the payload cannot be converted.
        """
        if self.context and not drop_context:
            raise PositionalContextNotSupportedError(
                'Packing to positional query with non-empty context is not allowed. '
                'Pass `drop_context=True` to not include context in packed query.'
            )

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
                return cls.model_validate(envelope.fields | {'context': envelope.context})

            base_field_names = set(CallbackData.model_fields.keys())
            field_names = [k for k in cls.model_fields.keys() if k not in base_field_names]
            return cls.model_validate(dict(zip(field_names, envelope.fields, strict=True)))
        except Exception as e:
            raise CallbackDataUnpackError(
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
        :raises PositionalContextNotSupportedError: If context is present and
            ``drop_context`` is false.
        :raises CallbackDataPackError: If serialization fails.
        """
        return self.to_positional_envelope(drop_context=drop_context).pack()

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
    def filter(cls) -> CallbackQueryFilter:
        """Create an aiogram filter for this callback model.

        :return: A filter that parses and validates matching callback queries.
        """
        from .filter import CallbackQueryFilter

        return CallbackQueryFilter(callback_data=cls)
