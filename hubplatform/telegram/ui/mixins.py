from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from aiogram.types import Message, CallbackQuery

if TYPE_CHECKING:
    from hubplatform.telegram.ui import MenuRenderResult, UIRegistry


class _MenuActionsMixin(ABC):
    @abstractmethod
    async def answer_to(
        self,
        aiogram_obj: Message | CallbackQuery | None = None,
        ui_registry: UIRegistry | None = None,
    ) -> None: pass

    @abstractmethod
    async def apply_to(
        self,
        aiogram_obj: Message | CallbackQuery | None = None,
        ui_registry: UIRegistry | None = None,
    ) -> None: pass


class _MenuContextActionsMixin(ABC, _MenuActionsMixin):
    @abstractmethod
    async def render(self, *, ui_registry: UIRegistry | None = None) -> MenuRenderResult: ...


class MenuActionsMixin(_MenuActionsMixin):
    @abstractmethod
    async def answer_to(
        self,
        aiogram_obj: Message | CallbackQuery | None = None,
        ui_registry: UIRegistry | None = None,
    ) -> None: pass