from __future__ import annotations


__all__ = ['GoodsSourcesManager', 'global_sources_manager']

from typing import Any
from asyncio import Lock
from functools import cache
from collections.abc import Callable, Iterator, KeysView, ValuesView

from .base import GoodsSource
from .exceptions import GoodsError, GoodsSourceNotFoundError


class GoodsSourcesManager:
    def __init__(self) -> None:
        self._sources: dict[str, GoodsSource] = {}
        self._lock = Lock()

    def get(self, source_id: str) -> GoodsSource | None:
        return self._sources.get(source_id)

    async def add_source[S: GoodsSource](
        self,
        source_factory: Callable[..., S],
        source: Any,
        *args: Any,
        **kwargs: Any,
    ) -> S:
        async with self._lock:
            source_instance = source_factory(source, *args, **kwargs)
            if source_instance.source_id in self._sources:
                raise ValueError(f'Source {source_instance.source_id} already exists.')

            await source_instance.load()
            self._sources[source_instance.source_id] = source_instance
            return source_instance

    async def remove_source(self, source_id: str) -> None:
        async with self._lock:
            if source_id not in self._sources:
                return

            source = self._sources[source_id]
            await source.remove()
            del self._sources[source_id]

    async def pop_goods(self, source_id: str, amount: int) -> list[str]:
        source = self.get(source_id)
        if source is None:
            raise GoodsSourceNotFoundError(source_id)

        try:
            return await source.pop_goods(amount)
        except GoodsError:
            raise
        except Exception as e:
            raise GoodsError('Unable to pop goods from source %s.', source_id) from e

    async def get_goods(self, source_id: str, amount: int, start: int = 0) -> list[str]:
        source = self.get(source_id)
        if source is None:
            raise GoodsSourceNotFoundError(source_id)

        try:
            return await source.get_goods(amount, start)
        except GoodsError:
            raise
        except Exception as e:
            raise GoodsError('Unable to get goods from source %s.', source_id) from e

    async def add_goods(self, source_id: str, goods: list[str]) -> None:
        source = self.get(source_id)
        if source is None:
            raise GoodsSourceNotFoundError(source_id)

        try:
            await source.add_goods(goods)
        except GoodsError:
            raise
        except Exception as e:
            raise GoodsError('Unable to add goods to %s.', source_id) from e

    def __len__(self) -> int:
        return len(self._sources)

    def __getitem__(self, key: str) -> GoodsSource:
        return self._sources[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._sources)

    def keys(self) -> KeysView[str]:
        return self._sources.keys()

    def values(self) -> ValuesView[GoodsSource]:
        return self._sources.values()


@cache
def global_sources_manager() -> GoodsSourcesManager:
    return GoodsSourcesManager()
