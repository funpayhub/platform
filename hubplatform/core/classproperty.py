from __future__ import annotations


__all__ = [
    'classproperty',
]


from typing import Generic, TypeVar, overload
from collections.abc import Callable


_T = TypeVar('_T')
_R_co = TypeVar('_R_co', covariant=True)


class classproperty(Generic[_T, _R_co]):
    def __init__(self, func: Callable[[type[_T]], _R_co], /) -> None:
        self._func = classmethod(func)

    @overload
    def __get__(self, obj: None, owner: type[_T], /) -> _R_co: ...

    @overload
    def __get__(self, obj: _T, owner: type[_T] | None = None, /) -> _R_co: ...

    def __get__(self, obj: _T | None, owner: type[_T] | None = None, /) -> _R_co:
        if owner is None:
            assert obj is not None
            owner = type(obj)

        return self._func.__get__(obj, owner)()
