from __future__ import annotations


__all__ = [
    'MenuBuilder',
    'ButtonBuilder',
    'MenuModification',
    'ButtonModification',
]

import inspect
from typing import Any, ClassVar
from collections.abc import Callable, Awaitable

from eventry.asyncio.callable_wrappers import CallableWrapper

from .types import Menu, ButtonSpec, MenuContext, ButtonContext


def _validate_identifier(cls: type[Any], value: str | None) -> str:
    if value is not None:
        if not isinstance(value, str):
            raise TypeError(f"'id' must be str, not {type(value).__name__!r}.")

        if not value:
            raise ValueError("'id' must not be empty.")

        return value

    if 'id' not in cls.__dict__:
        raise TypeError(f"{cls.__name__} must define 'id'.")
    return getattr(cls, 'id')


def _validate_context[T](cls: type[Any], ctx_type: type[T], value: Any) -> type[T]:
    if value is not None:
        if not isinstance(value, type) or not issubclass(value, ctx_type):
            raise TypeError(f"'context_type' must be a subclass of {ctx_type.__name__!r}.")
        return value
    return getattr(cls, 'context_type', ctx_type)


def _check_build(cls: type[Any]) -> None:
    build = getattr(cls, 'build', None)

    if build is None:
        raise TypeError(f"{cls.__name__} must implement 'build' method.")

    if not inspect.isfunction(build) or not inspect.iscoroutinefunction(build):
        raise TypeError(f'{cls.__name__}.build must be async method.')


class _Builder[O, C]:
    id: ClassVar[str]
    build: Callable[..., Awaitable[O]] | Callable[..., O]

    def __init__(self) -> None:
        self._wrapped: CallableWrapper[O] = CallableWrapper(self.build)

    async def __call__(self, ctx: C, data: dict[str, Any]) -> O:
        return await self._wrapped(args=[ctx], data=data)


class MenuBuilder(_Builder[Menu, MenuContext]):
    context_type: ClassVar[type[MenuContext]] = MenuContext

    def __init_subclass__(
        cls,
        *,
        id: str | None = None,
        context_type: type[MenuContext] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls.id = _validate_identifier(cls, id)
        cls.context_type = _validate_context(cls, MenuContext, context_type)
        _check_build(cls)


class ButtonBuilder(_Builder[ButtonSpec, ButtonContext]):
    context_type: ClassVar[type[ButtonContext]] = ButtonContext

    def __init_subclass__(
        cls,
        *,
        id: str | None = None,
        context_type: type[ButtonContext] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(**kwargs)
        cls.id = _validate_identifier(cls, id)
        cls.context_type = _validate_context(cls, ButtonContext, context_type)
        _check_build(cls)


_DUMMY_FILTER = CallableWrapper(lambda _, __: True)


class _Modification[O, C]:
    id: ClassVar[str]
    build: Callable[..., Awaitable[O]] | Callable[..., O]
    filter: Callable[..., Awaitable[bool]] | Callable[..., bool]

    def __init__(self) -> None:
        self._wrapped_modification: CallableWrapper[O] = CallableWrapper(self.build)
        filter = getattr(self, 'filter', None)
        self._wrapped_filter: CallableWrapper[bool] = (
            CallableWrapper(filter) if filter else _DUMMY_FILTER
        )

    async def __call__(self, context: C, obj: O, data: dict[str, Any]) -> O:
        if not (await self._wrapped_filter((context, obj), data)):
            return obj
        return await self._wrapped_modification((context, obj), data)

    @classmethod
    def _init_subclass(cls, id: str | None = None) -> None:
        cls.id = _validate_identifier(cls, id)
        _check_build(cls)


class MenuModification(_Modification[Menu, MenuContext]):
    def __init_subclass__(cls, id: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._init_subclass(id)


class ButtonModification(_Modification[ButtonSpec, ButtonContext]):
    def __init_subclass__(cls, id: str | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._init_subclass(id)
