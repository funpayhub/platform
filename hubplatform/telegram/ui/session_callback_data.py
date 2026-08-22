from __future__ import annotations


__all__ = [
    'SessionCallbackData',
    'session_context',
    'session_id_from_context',
    'revision_from_context',
]

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

from pydantic import Field

from hubplatform.telegram.callback_data import CallbackData

from .menu import SessionRef


_current_session: ContextVar[SessionRef | None] = ContextVar(
    'hubplatform_ui_session',
    default=None,
)


@contextmanager
def session_context(session: SessionRef | None) -> Iterator[None]:
    token = _current_session.set(session)
    try:
        yield
    finally:
        _current_session.reset(token)


def session_id_from_context() -> str:
    session = _current_session.get()
    if session is None:
        raise ValueError('session_id was not provided and there is no active UI session.')
    return session.session_id


def revision_from_context() -> int | None:
    session = _current_session.get()
    if session is None:
        return None
    return session.revision


class SessionCallbackData(CallbackData, identifier='hubplatform.session_callback'):
    session_id: str = Field(default_factory=session_id_from_context)
    revision: int | None = Field(default_factory=revision_from_context)
