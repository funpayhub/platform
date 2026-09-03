from __future__ import annotations

from aiogram import Bot
from pyconfigtree import Properties

from hubplatform.telegram import Dispatcher
from hubplatform.app_context import AppContext
from hubplatform.telegram.ui import UIManager, UIRegistry, global_ui_manager
from hubplatform.app.app_component import HubPlatformAppComponent
from hubplatform.telegram.commands import CommandsRegistry, global_commands_registry
from hubplatform.telegram.callback_data.hash import HashService

from . import TELEGRAM_APP_ROUTER, TELEGRAM_APP_UI_REGISTRY


class TelegramComponent(HubPlatformAppComponent):
    def __init__(
        self,
        token: str,
        *,
        dispatcher: Dispatcher | None = None,
        ui_manager: UIManager = global_ui_manager(),
        commands_registry: CommandsRegistry = global_commands_registry(),
    ) -> None:
        self._token = token
        self._dispatcher = dispatcher if dispatcher is not None else Dispatcher()
        self._ui_manager = ui_manager
        self._commands_registry = commands_registry
        self._bot = Bot(token=self._token)

        self._dispatcher.include_router(TELEGRAM_APP_ROUTER)
        self._ui_manager.ui_registry.merge_from(TELEGRAM_APP_UI_REGISTRY)

    @property
    def token(self) -> str:
        return self._token

    @property
    def bot(self) -> Bot:
        return self._bot

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    @property
    def ui_manager(self) -> UIManager:
        return self._ui_manager

    @property
    def ui_registry(self) -> UIRegistry:
        return self._ui_manager.ui_registry

    @property
    def hash_service(self) -> HashService:
        return self._ui_manager.hash_service

    @property
    def commands_registry(self) -> CommandsRegistry:
        return self._commands_registry

    async def run(self) -> None: ...

    async def stop(self) -> None: ...

    async def wait_stop(self) -> None: ...

    async def setup_context(self, context: AppContext) -> None:
        name = 'telegram_component'
        context.require(name, 'properties', lambda v: isinstance(v, Properties))
        context.require(name, 'telegram', lambda v: v is self)
        context.require(name, 'telegram_dispatcher', lambda v: v is self.dispatcher)
        context.require(name, 'telegram_bot', lambda v: v is self.bot)
        context.require(name, 'telegram_ui_manager', lambda v: v is self.ui_manager)
        context.require(name, 'telegram_ui_registry', lambda v: v is self.ui_registry)
        context.require(name, 'telegram_hash_service', lambda v: v is self.hash_service)

        context.provide(name, 'telegram', self)
        context.provide(name, 'telegram_dispatcher', self.dispatcher)
        context.provide(name, 'telegram_bot', self.bot)
        context.provide(name, 'telegram_ui_manager', self.ui_manager)
        context.provide(name, 'telegram_ui_registry', self.ui_registry)
        context.provide(name, 'telegram_hash_service', self.hash_service)
