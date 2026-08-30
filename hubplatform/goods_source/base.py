from __future__ import annotations


__all__ = ['GoodsSource']

from abc import ABC, abstractmethod
from collections.abc import Sequence


class GoodsSource(ABC):
    @abstractmethod
    async def load(self) -> None:
        pass

    @abstractmethod
    async def reload(self) -> None:
        pass

    @abstractmethod
    async def add_goods(self, products: Sequence[str]) -> None:
        pass

    @abstractmethod
    async def pop_goods(self, amount: int) -> list[str]:
        pass

    @abstractmethod
    async def get_goods(self, amount: int, start: int = 0) -> list[str]:
        pass

    @abstractmethod
    async def set_goods(self, goods: list[str]) -> None:
        pass

    @abstractmethod
    async def remove_goods(self, from_index: int, amount: int) -> None:
        pass

    @abstractmethod
    async def unload(self) -> None:
        pass

    @abstractmethod
    async def remove(self) -> None:
        pass

    @abstractmethod
    async def len(self) -> int:
        pass

    @property
    @abstractmethod
    def source_id(self) -> str:
        pass

    def __str__(self) -> str:
        return type(self).__name__
