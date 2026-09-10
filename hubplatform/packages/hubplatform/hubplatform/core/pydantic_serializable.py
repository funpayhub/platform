from __future__ import annotations


__all__ = [
    'PydanticSerializableMixin',
    'pydantic_fallback_serializer',
]

from typing import Any, TypeVar
from abc import ABCMeta, abstractmethod

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, PydanticSerializationError, core_schema


T = TypeVar('T')


class PydanticSerializableMixin(metaclass=ABCMeta):
    """Mixin for Pydantic-compatible string serialization.

    Subclasses must define how their instances are converted to strings and
    restored from strings by implementing :meth:`__pydantic_serialize__` and
    :meth:`__pydantic_deserialize__`.

    The mixin provides a Pydantic v2 core schema that supports:

    * accepting an existing instance of the subclass during Python validation;
    * creating an instance from a string during Python or JSON validation;
    * serializing an instance to a string during model serialization.

    .. code-block:: python
        class Coordinates(PydanticSerializableMixin):
            def __init__(self, x: int, y: int) -> None:
                self.x = x
                self.y = y

            def __pydantic_serialize__(self) -> str:
                return f'{self.x},{self.y}'

            @classmethod
            def __pydantic_deserialize__(
                cls,
                value: str,
            ) -> Coordinates:
                x, y = value.split(',', maxsplit=1)
                return cls(int(x), int(y))


        class Container(BaseModel):
            coordinates: Coordinates


        container = Container.model_validate({'coordinates': '10,20'})

        assert isinstance(callback.coordinates, Coordinates)
        assert callback.model_dump(mode='json') == {'coordinates': '10,20'}

    Note:
        When an object is serialized inside an untyped field such as
        ``dict[str, Any]``, its concrete Python type cannot generally be
        inferred from the resulting string during deserialization.

        Similarly, unions such as ``str | CustomType`` may be ambiguous when
        ``CustomType`` is also represented as a string. In such cases,
        Pydantic applies its normal union-validation rules.
    """

    @abstractmethod
    def __pydantic_serialize__(self) -> str:
        """Convert this instance to its string representation.

        The returned value is used by Pydantic when serializing a model that
        contains this object.

        The serialization format should be deterministic and should contain
        enough information for :meth:`__pydantic_deserialize__` to reconstruct
        an equivalent instance.
        :return: A string representation of this instance.
        """
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def __pydantic_deserialize__(cls: type[T], value: str) -> T:
        """Create an instance from its serialized string representation.

        Pydantic calls this method after validating that the input value is a string.

        Implementations should validate the complete input rather than silently
        accepting malformed or partially matching values.

        :param value: The serialized string representation to parse.
        :return: A reconstructed instance of the concrete subclass.
        :raises ValueError: If the value has an invalid format or contains invalid data.
        :raises TypeError: If the value cannot be used to construct an instance.
        """
        raise NotImplementedError()

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        from_string = core_schema.chain_schema(
            [
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(cls.__pydantic_deserialize__),
            ]
        )

        return core_schema.json_or_python_schema(
            json_schema=from_string,
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(cls),
                    from_string,
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: obj.__pydantic_serialize__(), return_schema=core_schema.str_schema()
            ),
        )


def pydantic_fallback_serializer(value: Any) -> str:
    if not isinstance(value, PydanticSerializableMixin):
        raise PydanticSerializationError(
            f'Instance of type {type(value).__name__!r} is not serializable.'
        )

    try:
        return value.__pydantic_serialize__()
    except Exception as e:
        raise PydanticSerializationError(
            f'An error occurred while serializing instance of type {type(value).__name__!r}: {e}'
        ) from e
