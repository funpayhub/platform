from __future__ import annotations


__all__ = ['ExpressionContext']

from typing import Any, ClassVar


class ExpressionContext:
    _available_context_types: ClassVar[tuple[type[ExpressionContext], ...]] = ()
    name: str = 'Root context'
    description: str = 'Root context'

    def __init_subclass__(
        cls,
        name: str | None = None,
        description: str | None = None, **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        if name is None:
            raise ValueError('Context name is not specified.')
        if description is None:
            raise ValueError('Context description is not specified.')

        cls.name = name
        cls.description = description

        context_base: type[ExpressionContext] | None = None
        for i in cls.__bases__:
            if issubclass(i, ExpressionContext):
                if context_base is None:
                    context_base = i
                    cls._available_context_types = (*i._available_context_types, cls)
                    continue

                raise TypeError(
                    'Expression context cannot be inherited from multiple context classes.'
                )

    @classmethod
    def get_available_context_types(cls) -> tuple[type[ExpressionContext], ...]:
        return cls._available_context_types


ExpressionContext._available_context_types = (ExpressionContext,)
