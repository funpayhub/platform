from __future__ import annotations


__all__ = [
    'InMemoryMenuSessionStorage',
]

from typing import Callable, AsyncGenerator
from dataclasses import field, dataclass
from time import monotonic
from random import randbytes
from asyncio import Lock
from contextlib import asynccontextmanager

from hubplatform.telegram.ui.session.types import MenuFrame, MenuSession

from .base import MenuSessionStorage
from .exceptions import (
    MenuSessionCreationError,
    MenuSessionNotFoundError,
    MenuSessionRevisionConflictError,
)


@dataclass
class _InMemorySessionEntry:
    session: MenuSession
    expires_at: int | None = None
    lock: Lock = field(default_factory=Lock)

    def is_expired(self, current: int | float) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < current


class InMemoryMenuSessionStorage(MenuSessionStorage):
    """In-memory, non-thread-safe menu session storage."""

    def __init__(
        self, ttl: int | None = 86400, clock: Callable[[], int | float] = monotonic
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._sessions: dict[str, _InMemorySessionEntry] = {}

    @property
    def ttl(self) -> int | None:
        return self._ttl

    async def _get_session(self, session_id: str) -> _InMemorySessionEntry:
        entry = self._sessions.get(session_id)

        if entry is None:
            raise MenuSessionNotFoundError(session_id)
        return entry

    def _ensure_same_session(
        self, session_id: str, session: _InMemorySessionEntry, update_ttl: bool = True
    ) -> None:
        current_session = self._sessions.get(session_id)
        if session is not current_session:
            raise MenuSessionNotFoundError(session_id)
        if update_ttl:
            session.expires_at = self._new_expiration()

    def _new_expiration(self) -> int | None:
        if self._ttl is None:
            return None
        return int(self._clock() + self._ttl)

    async def create(
        self,
        current: MenuFrame,
        chat_id: int | None = None,
        thread_id: int | None = None,
        message_id: int | None = None,
        history: list[MenuFrame] | None = None,
    ) -> MenuSession:
        history = [i.model_copy(deep=True) for i in history] if history is not None else []

        for i in range(10000):
            session_id = randbytes(16).hex()
            if session_id in self._sessions:
                continue

            entry = _InMemorySessionEntry(
                session=MenuSession(
                    id=session_id,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    current=current.model_copy(deep=True),
                    history=history,
                ),
                expires_at=self._new_expiration(),
            )

            out_session = entry.session.model_copy(deep=True)
            self._sessions[session_id] = entry
            return out_session
        else:
            raise MenuSessionCreationError(
                'An error occurred while creating new session: attempts exceeded.'
            )

    async def get(self, session_id: str) -> MenuSession:
        entry = await self._get_session(session_id)
        async with entry.lock:
            self._ensure_same_session(session_id, entry)
            return entry.session.model_copy(deep=True)

    @asynccontextmanager
    async def transaction(
        self,
        session_id: str,
        *,
        expected_revision: int | None = None,
    ) -> AsyncGenerator[MenuSession, None]:
        entry = await self._get_session(session_id)

        async with entry.lock:
            self._ensure_same_session(session_id, entry)
            current = entry.session

            if expected_revision is not None and expected_revision != current.revision:
                raise MenuSessionRevisionConflictError(
                    expected=expected_revision, actual=current.revision
                )

            draft = current.model_copy(deep=True)
            draft.revision = current.revision + 1

            yield draft

            self._ensure_same_session(session_id, entry)
            if current.id != draft.id:
                raise ValueError(f'Session ID changed from {session_id!r} to {draft.id!r}.')
            entry.session = draft.model_copy(deep=True)

    async def bind_message(
        self,
        session_id: str,
        chat_id: int | None = None,
        thread_id: int | None = None,
        message_id: int | None = None,
    ) -> MenuSession:
        session = await self._get_session(session_id)
        async with session.lock:
            self._ensure_same_session(session_id, session)

            session.session.message_id = message_id
            session.session.thread_id = thread_id
            session.session.chat_id = chat_id
            return session.session.model_copy(deep=True)

    async def delete(
        self,
        session_id: str,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False

        async with session.lock:
            if self._sessions.get(session_id) is not session:
                return False

            if expected_revision is not None and expected_revision != session.session.revision:
                raise MenuSessionRevisionConflictError(
                    expected=expected_revision,
                    actual=session.session.revision,
                )

            self._sessions.pop(session_id, None)
            return True

    async def purge_expired(self, force: bool = False) -> int:
        now = self._clock()
        to_remove: set[str] = set()
        for session_id, session in self._sessions.items():
            if session.lock.locked():
                if not force:
                    continue
            if session.is_expired(now):
                to_remove.add(session_id)

        for session_id in to_remove:
            del self._sessions[session_id]

        return len(to_remove)

    async def clear(self, force: bool = False) -> int:
        if force:
            length = len(self._sessions)
            self._sessions.clear()
            return length

        to_remove: set[str] = set()
        for session_id, session in self._sessions.items():
            if session.lock.locked():
                continue
            to_remove.add(session_id)

        for session_id in to_remove:
            del self._sessions[session_id]
        return len(to_remove)
