from __future__ import annotations


__all__ = [
    'MenuSessionError',
    'MenuSessionNotFoundError',
    'MenuSessionExpiredError',
    'MenuSessionAccessDeniedError',
    'MenuSessionRevisionConflictError',
    'MenuSessionAcquiredError',
    'MenuSessionCreationError',
]

from hubplatform.exceptions import HubPlatformError


class MenuSessionError(HubPlatformError):
    """Base error raised while working with a menu session."""


class MenuSessionNotFoundError(MenuSessionError):
    """The requested menu session does not exist."""


class MenuSessionExpiredError(MenuSessionError):
    """The requested menu session has expired."""


class MenuSessionAccessDeniedError(MenuSessionError):
    """The menu session does not belong to the callback source."""


class MenuSessionRevisionConflictError(MenuSessionError):
    """The action was created for an outdated menu session revision."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f'Expected revision {expected}, got {actual}.')


class MenuSessionAcquiredError(MenuSessionError):
    """The menu session is currently in use."""


class MenuSessionCreationError(MenuSessionError):
    """An error occurred while creating a menu session."""
