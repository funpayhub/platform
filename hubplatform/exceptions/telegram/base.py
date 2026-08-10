from __future__ import annotations


__all__ = [
    'TelegramError',
]

from hubplatform.exceptions.base import HubPlatformError


class TelegramError(HubPlatformError): ...
