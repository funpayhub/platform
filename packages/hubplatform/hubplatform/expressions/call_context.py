from __future__ import annotations


__all__ = ['ExpressionCallContext']


class ExpressionCallContext:
    def __init_subclass__(cls, **kwargs) -> None:
        has_context_base = False
        for i in cls.__bases__:
            if issubclass(i, ExpressionCallContext):
                if not has_context_base:
                    has_context_base = True
                    continue

                raise TypeError(
                    f'Expression context cannot be inherited from multiple context classes.'
                )
