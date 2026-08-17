from __future__ import annotations


__all__ = [
    'TelegramUIError',
    'MenuBuildingError',
    'MenuFinalizingError',
    'KeyboardBlockBuildingError',
    'KeyboardBlockModificationError',
    'ButtonRenderError',
]

from hubplatform.exceptions.base import HubPlatformError


class TelegramUIError(HubPlatformError): ...


class MenuBuildingError(TelegramUIError):
    def __init__(self, *, menu_id: str, message: str | None = None) -> None:
        self.menu_id = menu_id
        message = message if message is not None else f'Failed to build menu {menu_id!r}.'
        super().__init__(message)


class MenuFinalizingError(MenuBuildingError):
    def __init__(self, *, menu_id: str, message: str | None = None) -> None:
        message = message if message is not None else f'Failed to finalize menu {menu_id!r}.'
        super().__init__(menu_id=menu_id, message=message)


class KeyboardBlockBuildingError(TelegramUIError):
    def __init__(self, block_id: str, message: str | None = None) -> None:
        self.block_id = block_id
        message = (
            message if message is not None else f'Failed to build keyboard block {block_id!r}.'
        )
        super().__init__(message)


class KeyboardBlockModificationError(KeyboardBlockBuildingError):
    def __init__(self, block_id: str, modification_id: str, message: str | None = None) -> None:
        self.modification_id = modification_id
        message = (
            message
            if message is not None
            else f'Failed to run modification {modification_id!r} for keyboard block {block_id!r}.'
        )
        super().__init__(block_id=block_id, message=message)


class ButtonRenderError(TelegramUIError):
    def __init__(self, button_id: str, message: str | None = None) -> None:
        self.button_id = button_id
        message = message if message is not None else f'Failed to render button {button_id!r}.'
        super().__init__(message)
