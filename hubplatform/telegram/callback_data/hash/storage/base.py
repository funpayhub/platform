from __future__ import annotations


__all__ = [
    'HashStorage',
]


from abc import ABC, abstractmethod

from ..types import QueryHash


class HashStorage(ABC):
    @abstractmethod
    def setup(self) -> None: ...

    @abstractmethod
    def get_query(self, hash: str, update_ts: bool = True) -> QueryHash | None: ...

    @abstractmethod
    def save_queries(
        self,
        *hashes: QueryHash,
        truncate_stale: bool = True,
        truncate_excess: bool = True,
    ) -> None: ...

    @abstractmethod
    def truncate(self, stale: bool = True, excess: bool = True) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def stale_after(self) -> int: ...

    @property
    @abstractmethod
    def max_entries(self) -> int: ...
