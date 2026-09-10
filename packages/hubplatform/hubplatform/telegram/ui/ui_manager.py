from __future__ import annotations


__all__ = [
    'MenuDeliveryResult',
    'UIManager',
    'global_ui_manager',
]


from dataclasses import dataclass
from contextlib import suppress, asynccontextmanager
from collections.abc import AsyncGenerator

from aiogram import Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InputRichMessage,
    InaccessibleMessage,
)

from hubplatform.telegram.callback_data.hash import HashService, global_hash_service

from .menu import (
    SessionRef,
    MenuContext,
    MenuViewState,
    MenuEnvironment,
    MenuBuildContext,
    MenuRenderResult,
)
from .registry import UIRegistry, global_ui_registry
from .session.types import MenuFrame, MenuSession
from .session.storage import MenuSessionStorage, global_menu_session_storage
from .session.storage.exceptions import (
    MenuSessionNotFoundError,
    MenuSessionRevisionConflictError,
)


@dataclass(frozen=True, slots=True)
class MenuDeliveryResult:
    session: MenuSession
    menu: MenuRenderResult
    telegram_result: Message | bool


Trigger = Message | CallbackQuery
EnvironmentType = MenuEnvironment | Trigger


class UIManager:
    def __init__(
        self,
        ui_registry: UIRegistry,
        hash_service: HashService,
        session_storage: MenuSessionStorage,
    ) -> None:
        self._ui_registry = ui_registry
        self._hash_service = hash_service
        self._session_storage = session_storage

    @property
    def ui_registry(self) -> UIRegistry:
        return self._ui_registry

    @property
    def hash_service(self) -> HashService:
        return self._hash_service

    @property
    def session_storage(self) -> MenuSessionStorage:
        return self._session_storage

    @staticmethod
    def _actor_id_from_env(env: EnvironmentType | None) -> int | None:
        if env is None:
            return None
        if isinstance(env, MenuEnvironment):
            return env.actor_id
        if isinstance(env, Message):
            return env.from_user.id if env.from_user is not None else None
        if isinstance(env, CallbackQuery):
            return env.from_user.id
        return None

    @staticmethod
    def environment_from_obj(env: EnvironmentType) -> MenuEnvironment:
        if isinstance(env, MenuEnvironment):
            return env

        if isinstance(env, Message):
            return MenuEnvironment(
                chat_id=env.chat.id,
                thread_id=env.message_thread_id,
                message_id=env.message_id,
                actor_id=UIManager._actor_id_from_env(env),
            )

        message: Message | InaccessibleMessage | None = env.message
        return MenuEnvironment(
            chat_id=message.chat.id if message is not None else None,
            thread_id=message.message_thread_id if isinstance(message, Message) else None,
            message_id=message.message_id if message is not None else None,
            actor_id=env.from_user.id,
        )

    @staticmethod
    def _bot_from_environment(env: EnvironmentType | None, bot: Bot | None) -> Bot | None:
        if bot is not None:
            return bot
        if isinstance(env, (Message, CallbackQuery)):
            return env.bot
        return None

    @staticmethod
    def _environment_from_session(
        session: MenuSession, actor_id: int | None = None
    ) -> MenuEnvironment:
        return MenuEnvironment(
            chat_id=session.chat_id,
            thread_id=session.thread_id,
            message_id=session.message_id,
            actor_id=actor_id,
        )

    async def _build(
        self,
        *,
        menu_id: str,
        context: MenuContext,
        view_state: MenuViewState,
        environment: MenuEnvironment | None,
        history: list[MenuFrame] | None = None,
        session: SessionRef | None,
    ) -> MenuRenderResult:
        result = await self.ui_registry.build_menu(
            menu_id=menu_id,
            menu_context=MenuBuildContext(
                menu_id=menu_id,
                context=context,
                environment=environment,
                session=session,
                view_state=view_state,
                history=tuple(history) if history is not None else (),
            ),
            hash_service=self.hash_service,
        )
        # Callback hashes must be persisted before Telegram exposes the keyboard.
        self.hash_service.save()
        return result

    async def _build_session(
        self, session: MenuSession, actor_id: int | None = None
    ) -> MenuRenderResult:
        context_type = self.ui_registry.get_menu_context_type(session.current.menu_id)
        context = context_type.model_validate(session.current.context_fields)

        return await self._build(
            menu_id=session.current.menu_id,
            context=context,
            view_state=MenuViewState(
                keyboard_page=session.current.keyboard_page,
                text_page=session.current.text_page,
            ),
            environment=self._environment_from_session(session, actor_id=actor_id),
            session=SessionRef(session_id=session.id, revision=session.revision),
            history=session.history,
        )

    async def _rerender_session(
        self,
        session: MenuSession,
        trigger: Trigger | None = None,
        bot: Bot | None = None,
        actor_id: int | None = None,
    ) -> MenuDeliveryResult:
        if session.chat_id is None or session.message_id is None:
            raise ValueError('Cannot render a session not bound to a message.')

        if actor_id is None and trigger is not None:
            actor_id = self._actor_id_from_env(trigger)

        if (bot := self._bot_from_environment(trigger, bot)) is None:
            raise ValueError(
                'Cannot rerender session: '
                'Bot instance was neither found in the trigger object nor explicitly provided.'
            )

        menu = await self._build_session(session, actor_id=actor_id)
        telegram_result = await bot.edit_message_text(
            chat_id=session.chat_id,
            message_id=session.message_id,
            rich_message=InputRichMessage(html=menu.text),
        )
        return MenuDeliveryResult(
            session=session.model_copy(deep=True),
            menu=menu,
            telegram_result=telegram_result,
        )

    async def _create_and_deliver_session(
        self,
        *,
        bot: Bot,
        current: MenuFrame,
        context: MenuContext,
        environment: MenuEnvironment,
        history: list[MenuFrame] | None = None,
    ) -> MenuDeliveryResult:
        if environment.chat_id is None:
            raise ValueError('Cannot deliver a session without a chat ID.')

        session = await self.session_storage.create(
            current=current.model_copy(deep=True),
            chat_id=environment.chat_id,
            thread_id=environment.thread_id,
            history=[frame.model_copy(deep=True) for frame in (history or ())],
        )

        try:
            menu = await self._build(
                menu_id=current.menu_id,
                context=context,
                view_state=MenuViewState(
                    keyboard_page=current.keyboard_page,
                    text_page=current.text_page,
                ),
                environment=environment,
                session=SessionRef(session_id=session.id, revision=session.revision),
                history=[frame.model_copy(deep=True) for frame in session.history],
            )
            sent_message = await bot.send_rich_message(
                chat_id=environment.chat_id,
                message_thread_id=environment.thread_id,
                rich_message=InputRichMessage(html=menu.text),
            )
            session = await self.session_storage.bind_message(
                session_id=session.id,
                chat_id=sent_message.chat.id,
                thread_id=sent_message.message_thread_id,
                message_id=sent_message.message_id,
            )
        except BaseException:
            with suppress(Exception):
                await self.session_storage.delete(session.id)
            raise

        return MenuDeliveryResult(session=session, menu=menu, telegram_result=sent_message)

    async def render_menu(
        self,
        menu_id: str,
        context: MenuContext,
        *,
        environment: MenuEnvironment | Message | CallbackQuery | None = None,
        view_state: MenuViewState | None = None,
        history: list[MenuFrame] | None = None,
    ) -> MenuRenderResult:
        return await self._build(
            menu_id=menu_id,
            context=context,
            view_state=view_state or MenuViewState(),
            environment=(
                self.environment_from_obj(environment) if environment is not None else None
            ),
            history=history,
            session=None,
        )

    async def render_session(
        self,
        session_id: str,
        trigger: Trigger | None = None,
        *,
        actor_id: int | None = None,
    ) -> MenuRenderResult:
        return await self._build_session(
            session=await self.session_storage.get(session_id),
            actor_id=actor_id if actor_id is not None else self._actor_id_from_env(trigger),
        )

    async def rerender_session(
        self,
        session_id: str,
        trigger: Trigger | None = None,
        *,
        bot: Bot | None = None,
        actor_id: int | None = None,
        expected_revision: int | None = None,
    ) -> MenuDeliveryResult:
        session = await self.session_storage.get(session_id)
        if expected_revision is not None and expected_revision != session.revision:
            raise MenuSessionRevisionConflictError(
                expected=expected_revision,
                actual=session.revision,
            )

        return await self._rerender_session(session, trigger, bot=bot, actor_id=actor_id)

    async def open_menu(
        self,
        menu_id: str,
        context: MenuContext,
        environment: EnvironmentType,
        *,
        bot: Bot | None = None,
        view_state: MenuViewState | None = None,
    ) -> MenuDeliveryResult:
        bot = self._bot_from_environment(environment, bot)
        if bot is None:
            raise ValueError(
                'Cannot open menu: '
                'Bot instance was neither found in the environment object nor explicitly provided.'
            )

        environment = self.environment_from_obj(environment)
        if environment.chat_id is None:
            raise ValueError(
                'Cannot open menu: chat ID was not provided in the environment object.'
            )

        return await self._create_and_deliver_session(
            bot=bot,
            current=MenuFrame.from_menu_context(menu_id, context, view_state or MenuViewState()),
            context=context,
            environment=environment,
        )

    async def clone_session(
        self, session_id: str, environment: EnvironmentType, *, bot: Bot | None = None
    ) -> MenuDeliveryResult:
        bot = self._bot_from_environment(environment, bot)
        if bot is None:
            raise ValueError(
                'Cannot clone session: '
                'Bot instance was neither found in the environment object nor explicitly provided.'
            )

        environment = self.environment_from_obj(environment)
        if environment.chat_id is None:
            raise ValueError(
                'Cannot clone session: chat ID was not provided in the environment object.'
            )

        source = await self.session_storage.get(session_id)
        context_type = self.ui_registry.get_menu_context_type(source.current.menu_id)
        context = context_type.model_validate(source.current.context_fields)

        return await self._create_and_deliver_session(
            bot=bot,
            current=source.current,
            context=context,
            environment=environment,
            history=source.history,
        )

    async def replace_menu(
        self,
        session_id: str,
        menu_id: str,
        context: MenuContext,
        trigger: Trigger | None = None,
        *,
        bot: Bot | None = None,
        view_state: MenuViewState | None = None,
        push_current_to_history: bool = True,
        expected_revision: int | None = None,
        actor_id: int | None = None,
    ) -> MenuDeliveryResult:
        bot = self._bot_from_environment(trigger, bot)
        if bot is None:
            raise ValueError(
                'Cannot replace menu: '
                'Bot instance was neither found in the environment object nor explicitly provided.'
            )

        async with self.session_storage.transaction(
            session_id=session_id,
            expected_revision=expected_revision,
        ) as session:
            if session.chat_id is None or session.message_id is None:
                raise ValueError('Cannot replace a menu in a session not bound to a message.')

            if push_current_to_history:
                session.history.append(session.current)

            session.current = MenuFrame.from_menu_context(
                menu_id, context, view_state if view_state is not None else MenuViewState()
            )
            return await self._rerender_session(
                session=session,
                trigger=trigger,
                bot=bot,
                actor_id=actor_id,
            )

    async def close_session(
        self,
        session_id: str,
        trigger: Trigger | None = None,
        *,
        bot: Bot | None = None,
        delete_message: bool = True,
        expected_revision: int | None = None,
    ) -> bool:
        try:
            session = await self.session_storage.get(session_id)
        except MenuSessionNotFoundError:
            return False

        r = await self.session_storage.delete(session_id, expected_revision=expected_revision)
        if not r:
            return False

        if delete_message:
            with suppress(Exception):
                bot = self._bot_from_environment(trigger, bot)
                await bot.delete_message(chat_id=session.chat_id, message_id=session.message_id)  # type: ignore
        return True

    @asynccontextmanager
    async def edit_session(
        self,
        session_id: str,
        trigger: Trigger | None = None,
        *,
        expected_revision: int | None = None,
        rerender: bool = False,
        bot: Bot | None = None,
        actor_id: int | None = None,
    ) -> AsyncGenerator[MenuSession, None]:
        resolved_bot = self._bot_from_environment(trigger, bot)
        if rerender and resolved_bot is None:
            raise ValueError('Bot is not bound to environment and was not passed.')

        async with self.session_storage.transaction(
            session_id=session_id,
            expected_revision=expected_revision,
        ) as session:
            yield session
            if rerender:
                await self._rerender_session(
                    session=session,
                    trigger=trigger,
                    bot=resolved_bot,
                    actor_id=actor_id,
                )


_GLOBAL_UI_MANAGER: UIManager | None = None


def global_ui_manager() -> UIManager:
    global _GLOBAL_UI_MANAGER
    if _GLOBAL_UI_MANAGER is None:
        _GLOBAL_UI_MANAGER = UIManager(
            ui_registry=global_ui_registry(),
            hash_service=global_hash_service(),
            session_storage=global_menu_session_storage(),
        )
    return _GLOBAL_UI_MANAGER
