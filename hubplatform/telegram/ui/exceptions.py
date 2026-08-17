from __future__ import annotations


__all__ = [
    'TelegramUIError',
    'MenuBuildingError',
    'KeyboardBlockBuildingError',
]

from hubplatform.exceptions.base import HubPlatformError


class TelegramUIError(HubPlatformError): ...


class MenuBuildingError(TelegramUIError): ...


class KeyboardBlockBuildingError(TelegramUIError): ...
