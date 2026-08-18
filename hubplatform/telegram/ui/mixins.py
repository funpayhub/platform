from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from aiogram.types import Message, CallbackQuery

if TYPE_CHECKING:
    from hubplatform.telegram.ui import MenuRenderResult, UIRegistry
