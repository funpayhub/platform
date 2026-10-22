from __future__ import annotations


__all__ = ['ExpressionCallContext']

from typing import Any, ClassVar


class ExpressionCallContext:
    _available_context_types: ClassVar[tuple[type[ExpressionCallContext], ...]] = tuple()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        context_base: type[ExpressionCallContext] | None = None
        for i in cls.__bases__:
            if issubclass(i, ExpressionCallContext):
                if context_base is None:
                    context_base = i
                    cls._available_context_types = (*i._available_context_types, cls)
                    continue

                raise TypeError(
                    'Expression context cannot be inherited from multiple context classes.'
                )

ExpressionCallContext._available_context_types = (ExpressionCallContext, )
