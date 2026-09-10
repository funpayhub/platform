from __future__ import annotations


__all__ = [
    'MenuSessionStorage',
]


from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from hubplatform.telegram.ui.session.types import MenuFrame, MenuSession


class MenuSessionStorage(ABC):
    @abstractmethod
    async def create(
        self,
        current: MenuFrame,
        chat_id: int | None = None,
        thread_id: int | None = None,
        message_id: int | None = None,
        history: list[MenuFrame] | None = None,
    ) -> MenuSession:
        pass

    @abstractmethod
    async def get(self, session_id: str) -> MenuSession:
        pass

    @abstractmethod
    async def delete(
        self,
        session_id: str,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        pass

    @abstractmethod
    async def bind_message(
        self,
        session_id: str,
        chat_id: int | None = None,
        thread_id: int | None = None,
        message_id: int | None = None,
    ) -> MenuSession:
        pass

    @abstractmethod
    def transaction(
        self,
        session_id: str,
        *,
        expected_revision: int | None = None,
    ) -> AbstractAsyncContextManager[MenuSession]:
        pass

    @abstractmethod
    async def clear(self, force: bool = False) -> int:
        pass

    @abstractmethod
    async def purge_expired(self, force: bool = False) -> int:
        pass
