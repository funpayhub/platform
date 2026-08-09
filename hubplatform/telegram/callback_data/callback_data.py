from __future__ import annotations


__all__ = [
    'CallbackData',
    'CallbackQueryFilter',
]

import json
import string
from typing import Any, Type, Literal, TypeVar, ClassVar, Annotated

from pydantic import (
    Field,
    BaseModel,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from aiogram.types import CallbackQuery
from aiogram.filters import Filter

from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer

from . import HashService
from .hash.service import global_hash_service


T = TypeVar('T', bound='CallbackData')


_ALLOWED = set(string.ascii_letters + string.digits + '._-')


class CallbackData(BaseModel):
    __identifier__: ClassVar[str] = ''

    identifier: Annotated[str, Field(min_length=1, frozen=True)] = ''
    data: dict[str, Any] = Field(default_factory=dict)
    positional_data: list[Any] = Field(default_factory=list)
    compact: bool = Field(default=False, frozen=True)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if not (identifier := kwargs.pop('identifier', None)):
            raise ValueError(
                f'Identifier required. Example: '
                f"`class {cls.__name__}(CallbackData, identifier='my_callback'): ...`",
            )

        cls.__identifier__ = identifier
        super().__init_subclass__(**kwargs)

    @field_validator('identifier', mode='before')
    @classmethod
    def _check_identifier_matches(cls, value: str) -> str:
        if not cls.__identifier__:
            if not value:
                raise ValidationError('Identifier not provided.')  # todo
            return value

        if not value:
            return cls.__identifier__
        if value != cls.__identifier__:
            raise ValidationError('identifier mismatch')  # todo
        return value

    @field_validator('positional_data', mode='after')
    @classmethod
    def _check_no_positional_data(cls, value: tuple[Any]) -> tuple[Any]:
        if cls is not CallbackData and value:
            raise ValueError(
                '`.positional_data` of real callback data must be empty! '
                'All data must me assigned to the model fields.'
            )
        return value

    @classmethod
    def _hash_service(cls, hash_service: HashService | None = None) -> HashService:
        return hash_service if hash_service is not None else global_hash_service()

    def pack(self, hash: bool = True, hash_service: HashService | None = None) -> str:
        data = self.model_dump(
            mode='json',
            exclude={'compact', 'identifier', 'positional_data'},
            fallback=pydantic_fallback_serializer,
        )
        if type(self) is CallbackData:
            data = data.pop('data', {})

        data_str = (
            ''
            if not data
            else json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        )
        result = self.identifier + data_str

        if hash:
            self._hash_service(hash_service).hash(result)
        return result

    def pack_compact(self, drop_data: bool = False) -> str:
        if self.data and not drop_data:
            raise RuntimeError(
                f'Instance of {self.__class__.__name__} cannot be packed compactly: '
                f'data is not empty. Pass `drop_data`=`True` to drop it.',
            )

        dump = self.model_dump(mode='json', exclude={'compact', 'identifier', 'data'})
        if type(self) is CallbackData:
            positional_data = dump.pop('positional_data', [])
        else:
            positional_data = [
                v for k, v in self.model_fields.items()
                if k not in CallbackData.model_fields.keys()
            ]

        if not positional_data:
            data_str = ''
        else:
            data_str = ';'.join(self._serialize_value_for_compact_repr(v) for v in positional_data)

        result = f'!{self.identifier}' + (f':{data_str}' if data_str else '')

        if len(result) > 64:
            raise ValueError(f'Compacted callback data is too long ({len(result)} > 64).')
        return result

    def _serialize_value_for_compact_repr(self, value: Any) -> str:
        if type(value) is bool:
            return str(int(value))
        if type(value) in (int, float):
            return str(value)

        if type(value) is str:
            result = value
        else:
            type_adapter = TypeAdapter(type(value))
            try:
                result = type_adapter.dump_python(value, mode='json').decode('utf-8')
            except Exception as e:
                raise ValueError(f'Unable to serialize value of {type(value).__name__!r}.') from e

        if isinstance(result, str):
            result = result.replace('%', '%P').replace(':', '%S')
        return result

    @classmethod
    def parse(cls, value: str, hash_service: HashService | None = None) -> CallbackData:
        hash_service = cls._hash_service(hash_service)
        if hash_service.is_hash(value):
            value = hash_service.unhash(value).query

        if cls.is_compact(value):
            identifier, _, data = value[1:].partition(':')
            positional = [i.replace('%S', ':').replace('%P', '%') for i in data.split(':')]
            return CallbackData(identifier=identifier, positional_data=positional, compact=True)

        identifier, sep, raw = value.partition('{')
        data = json.loads(sep + raw) if raw else {}
        return CallbackData(identifier=identifier, data=data)

    @classmethod
    def unpack(cls: Type[T], value: str | CallbackData) -> T:
        if isinstance(value, str):
            value = cls.parse(value)

        if cls is CallbackData:
            return value

        cb_model_names = [
            i for i in cls.model_fields.keys() if i not in CallbackData.model_fields.keys()
        ]

        if value.compact:
            if len(value.positional_data) != len(cb_model_names):
                raise ValueError(
                    f'Values amount ({len(value.positional_data)}) != fields amount '
                    f'({len(cb_model_names)}).',
                )
            return cls(
                identifier=value.identifier, **dict(zip(cb_model_names, value.positional_data))
            )

        required_fields = {
            name
            for name, field in cls.model_fields.items()
            if name not in cb_model_names and field.is_required()
        }

        if required_fields > value.data.keys():
            missing = required_fields - value.data.keys()
            raise TypeError(f'Fields {", ".join(missing)} are missing.')

        data = {}
        model_fields = {}
        for k, v in value.data.items():
            if k in cb_model_names:
                model_fields[k] = v
            else:
                data[k] = v

        return cls(
            identifier=value.identifier,
            data=data,
            **model_fields,
        )

    @classmethod
    def is_compact(cls, value: str) -> bool:
        return value.startswith('!')

    @classmethod
    def filter(cls) -> CallbackQueryFilter:
        """
        Generates a filter for callback query with rule

        :return: instance of filter
        """
        return CallbackQueryFilter(callback_data=cls)


class CallbackQueryFilter(Filter):
    """
    This filter helps to handle callback query.

    Should not be used directly, you should create the instance of this filter
    via callback data instance
    """

    def __init__(self, *, callback_data: Type[CallbackData]) -> None:
        """
        :param callback_data: Expected type of callback data
        """
        self.callback_data = callback_data

    async def __call__(self, query: CallbackQuery | str) -> Literal[False] | dict[str, Any]:
        if not isinstance(query, CallbackQuery | str):
            return False
        data = query if isinstance(query, str) else query.data
        if not data:
            return False

        try:
            unpacked = getattr(query, '__parsed__', None)
            if unpacked is None:
                unpacked = self.callback_data.parse(data)
                if isinstance(query, CallbackQuery):
                    query.__dict__['__parsed__'] = unpacked
            callback_data = self.callback_data.unpack(unpacked)
            return {'callback_data': callback_data, 'cbd': callback_data}
        except (TypeError, ValueError):
            unpacked = getattr(query, '__parsed__', None)
            if unpacked.identifier == self.callback_data.__identifier__:
                pass
            return False
