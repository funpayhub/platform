from __future__ import annotations

from typing import Any, TypeVar
from abc import ABCMeta, abstractmethod

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema


T = TypeVar('T')


class PydanticSerializableMixin(metaclass=ABCMeta):
    @abstractmethod
    def __pydantic_serialize__(self) -> str:
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def __pydantic_deserialize__(cls: type[T], value: str) -> T:
        raise NotImplementedError()

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        from_string = core_schema.chain_schema([
            core_schema.str_schema(),
            core_schema.no_info_plain_validator_function(cls.__pydantic_deserialize__)
        ])

        return core_schema.json_or_python_schema(
            json_schema=from_string,
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(cls),
                from_string,
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: obj.__pydantic_serialize__(),
                return_schema=core_schema.str_schema()
            )
        )
