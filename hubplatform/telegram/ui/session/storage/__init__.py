from __future__ import annotations


__all__ = [
    'MenuSessionStorage',
    'InMemoryMenuSessionStorage',
    'global_menu_session_storage',
]


from .base import MenuSessionStorage
from .inmemory import InMemoryMenuSessionStorage


_GLOBAL_SESSION_STORAGE: InMemoryMenuSessionStorage | None = None


def global_menu_session_storage() -> MenuSessionStorage:
    global _GLOBAL_SESSION_STORAGE
    if _GLOBAL_SESSION_STORAGE is None:
        _GLOBAL_SESSION_STORAGE = InMemoryMenuSessionStorage()
    return _GLOBAL_SESSION_STORAGE
