from __future__ import annotations


__all__ = ['ExpressionContext']

from typing import Any, ClassVar


class ExpressionContext:
    _available_context_types: ClassVar[tuple[type[ExpressionContext], ...]] = tuple()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
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
