from __future__ import annotations


__all__ = ['convert_exceptions']


from typing import Callable, AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def convert_exceptions(
    except_: type[Exception],
    exception_factory: Callable[[], Exception],
) -> AsyncGenerator[None, None]:
    try:
        yield
    except Exception as e:
        if isinstance(e, except_):
            raise
        raise exception_factory() from e
