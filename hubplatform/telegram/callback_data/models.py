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

from hubplatform.telegram.callback_data import global_hash_service
from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer


if TYPE_CHECKING:
    from hubplatform.telegram.callback_data.hash import HashService

    from .filter import CallbackQueryFilter


_ALLOWED_IDENTIFIER_SYMBOLS = frozenset(string.ascii_letters + string.digits + '._-')


def validate_identifier(identifier: str) -> str:
    if not identifier:
        raise ValueError('Callback identifier cannot be empty.')
    invalid_symbols = set(identifier) - _ALLOWED_IDENTIFIER_SYMBOLS
    if invalid_symbols:
        symbols = ''.join(sorted(invalid_symbols))
        raise ValueError(f'Callback identifier contains invalid symbols: {symbols!r}.')
    return identifier


def _hash_service(hash_service: HashService | None) -> HashService:
    return hash_service if hash_service is not None else global_hash_service()


class CallbackEnvelope(BaseModel, ABC):
    identifier: Annotated[str, AfterValidator(validate_identifier)]

    @abstractmethod
    def pack(self, *, hash: bool = True, hash_service: HashService | None = None) -> str: ...

    @classmethod
    @abstractmethod
    def unpack(
        cls, query: str, *, check_is_hash: bool = True, hash_service: HashService | None = None
    ) -> CallbackEnvelope: ...


class KeywordCallbackEnvelope(CallbackEnvelope):
    fields: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    def pack(self, *, hash: bool = True, hash_service: HashService | None = None) -> str:
        data = self.model_dump(mode='json', fallback=pydantic_fallback_serializer)

        data_str = json.dumps(
            [data['fields'], data['context']],
            ensure_ascii=False,
            separators=(',', ':'),
        )

        result = self.identifier + data_str

        if hash:
            result = _hash_service(hash_service).hash(result)
        return result

    @classmethod
    def unpack(
        cls, query: str, *, check_is_hash: bool = True, hash_service: HashService | None = None
    ) -> KeywordCallbackEnvelope:
        if check_is_hash:
            hash_service = _hash_service(hash_service)
            if hash_service.is_hash(query):
                query = hash_service.unhash(query).query

        identifier, sep, data = query.partition('[')
        if not sep:
            raise ValueError('Cant parse it')  # todo
        fields, context = json.loads(sep + data)
        return KeywordCallbackEnvelope(identifier=identifier, fields=fields, context=context)


class PositionalCallbackEnvelope(CallbackEnvelope):
    fields: list[Any] = Field(default_factory=list)

    def pack(self, *, hash: bool = True, hash_service: HashService | None = None) -> str:
        fields = self.model_dump(mode='json')['fields']
        if not fields:
            result = f'!{self.identifier}'
        else:
            result = f'!{self.identifier}:' + ':'.join(self._serialize_value(i) for i in fields)
        return result

    @classmethod
    def unpack(
        cls, query: str, *, check_is_hash: bool = True, hash_service: HashService | None = None
    ) -> PositionalCallbackEnvelope:
        if not cls.is_positional_query(query):
            raise ValueError(f'{query!r} is not a positional callback query.')

        identifier, sep, fields = query[1:].partition(':')
        if sep:
            positional = [i.replace('%S', ':').replace('%P', '%') for i in fields.split(':')]
        else:
            positional = []
        return PositionalCallbackEnvelope(identifier=identifier, fields=positional)

    def _serialize_value(self, value: Any) -> str:
        if type(value) is bool:
            return str(int(value))
        if type(value) in (int, float):
            return str(value)
        if type(value) is str:
            return value.replace('%', '%P').replace(':', '%S')

        raise ValueError(f'Unable to serialize value of {type(value).__name__!r}.')

    @staticmethod
    def is_positional_query(query: str) -> bool:
        return query.startswith('!') and len(query) <= 64


ParsedEnvelope = KeywordCallbackEnvelope | PositionalCallbackEnvelope


class CallbackData(BaseModel):
    """Base class for concrete, typed callback payloads."""

    identifier: ClassVar[str] = ''
    context: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, context: Any, /) -> None:
        validate_identifier(self.identifier)

    def __init_subclass__(cls, **kwargs: Any) -> None:
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
        return self.model_dump(
            mode='json',
            exclude=set(CallbackData.model_fields.keys()),
            fallback=pydantic_fallback_serializer,
        )

    def to_keyword_envelope(self) -> KeywordCallbackEnvelope:
        return KeywordCallbackEnvelope(
            identifier=self.identifier, fields=self._dump_callback_fields(), context=self.context
        )

    def to_positional_envelope(self, *, drop_context: bool = False) -> PositionalCallbackEnvelope:
        if self.context and not drop_context:
            raise RuntimeError(
                'Cant create PositionalCallbackEnvelope with non-empty context.'
            )  # todo

        return PositionalCallbackEnvelope(
            identifier=self.identifier, fields=list(self._dump_callback_fields().values())
        )

    @classmethod
    def from_envelope(cls, envelope: ParsedEnvelope) -> Self:
        if envelope.identifier != cls.identifier:
            raise ValueError('Identifier mismatch.')

        if isinstance(envelope, KeywordCallbackEnvelope):
            return cls.model_validate(envelope.fields | {'context': envelope.context})

        base_field_names = set(CallbackData.model_fields.keys())
        field_names = [k for k in cls.model_fields.keys() if k not in base_field_names]
        return cls.model_validate(dict(zip(field_names, envelope.fields, strict=True)))

    def pack(self, *, hash: bool = True, hash_service: HashService | None = None) -> str:
        envelope = self.to_keyword_envelope()
        return envelope.pack(hash=hash, hash_service=hash_service)

    def pack_compact(self, *, drop_context: bool = False) -> str:
        envelope = self.to_positional_envelope(drop_context=drop_context)
        return envelope.pack(hash=False)

    @classmethod
    def unpack(
        cls,
        query: str | ParsedEnvelope,
        *,
        check_is_hash: bool = True,
        hash_service: HashService | None = None,
    ) -> Self:
        if isinstance(query, str):
            if PositionalCallbackEnvelope.is_positional_query(query):
                query = PositionalCallbackEnvelope.unpack(
                    query, check_is_hash=check_is_hash, hash_service=hash_service
                )
            else:
                query = KeywordCallbackEnvelope.unpack(
                    query, check_is_hash=check_is_hash, hash_service=hash_service
                )

        return cls.from_envelope(query)

    @classmethod
    def filter(cls) -> CallbackQueryFilter:
        from .filter import CallbackQueryFilter

        return CallbackQueryFilter(callback_data=cls)
