__all__ = [
    'HashStorage',
]


from abc import ABC, abstractmethod
from typing import overload


class HashStorage(ABC):
    @abstractmethod
    async def get_callback(self, hash: str, update_ts: bool = True) -> str | None:
        ...

    @abstractmethod
    async def update_ts(self, *hashes: str) -> None:
        ...

    @abstractmethod
    async def save_callbacks(
        self,
        hashes: dict[str, str],
        update_ts: bool = True,
        truncate_stale: bool = True,
        truncate_excess: bool = True,
    ) -> None:
        ...

    @abstractmethod
    async def truncate_stale(self) -> None: ...

    @abstractmethod
    async def truncate_excess(self) -> None: ...

    @abstractmethod
    async def truncate(self) -> None: ...

    @overload
    async def get_ts(self, hash: str, /) -> int: ...

    @overload
    async def get_ts(self, hash1: str, hash2: str, /, *hashes: str) -> list[int]: ...

    @abstractmethod
    async def get_ts(self, *hashes: str) -> int: ...

    @abstractmethod
    @property
    def stale_after_seconds(self) -> int: ...

    @abstractmethod
    def max_entries(self) -> int: ...
