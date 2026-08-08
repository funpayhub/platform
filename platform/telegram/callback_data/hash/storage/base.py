from __future__ import annotations


__all__ = [
    'HashStorage',
]


from abc import ABC, abstractmethod

from ..types import QueryHash


class HashStorage(ABC):
    async def setup(self) -> None: ...

    @abstractmethod
    async def get_callback(self, hash: str, update_ts: bool = True) -> QueryHash | None: ...

    @abstractmethod
    async def save_callbacks(
        self,
        *hashes: QueryHash,
        truncate_stale: bool = True,
        truncate_excess: bool = True,
    ) -> None: ...

    @abstractmethod
    async def truncate(self, stale: bool = True, excess: bool = True) -> None: ...

    @abstractmethod
    @property
    def stale_after(self) -> int: ...

    @abstractmethod
    @property
    def max_entries(self) -> int: ...
