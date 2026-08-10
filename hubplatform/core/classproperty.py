from __future__ import annotations

from typing import Generic, TypeVar, overload
from collections.abc import Callable


T = TypeVar('T')
R_co = TypeVar('R_co', covariant=True)


class classproperty(Generic[T, R_co]):
    def __init__(self, func: Callable[[type[T]], R_co], /) -> None:
        self._func = classmethod(func)

    @overload
    def __get__(self, obj: None, owner: type[T], /) -> R_co: ...

    @overload
    def __get__(self, obj: T, owner: type[T] | None = None, /) -> R_co: ...

    def __get__(self, obj: T | None, owner: type[T] | None = None, /) -> R_co:
        if owner is None:
            assert obj is not None
            owner = type(obj)

        return self._func.__get__(obj, owner)()
