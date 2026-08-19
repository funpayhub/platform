from __future__ import annotations


__all__ = [
    'extract_runtime',
    'apply_menu',
    'apply_menu_context',
    'apply_menu_snapshot',
]


from aiogram import Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InputRichMessage,
    InaccessibleMessage,
    InlineKeyboardMarkup,
)
from aiogram.client.context_controller import BotContextController

from hubplatform.telegram.ui.types import (
    MenuContext,
    MenuRenderResult,
    MenuRuntimeContext,
    MenuContextSnapshot,
)
from hubplatform.telegram.ui.registry import UIRegistry, global_ui_registry


def extract_runtime(obj: object) -> MenuRuntimeContext:
    msg: Message | InaccessibleMessage | None = None
    user_id: int | None = None

    if isinstance(obj, Message):
        msg = obj
        user_id = obj.from_user.id if obj.from_user is not None else None
    elif isinstance(obj, CallbackQuery):
        msg = obj.message
        user_id = obj.from_user.id

    if msg is None:
        return MenuRuntimeContext()

    return MenuRuntimeContext(
        chat_id=msg.chat.id,
        thread_id=msg.message_thread_id if isinstance(msg, Message) else None,
        message_id=msg.message_id,
        user_id=user_id,
    )


async def apply_menu(
    menu: MenuRenderResult,
    target: BotContextController,
    *,
    bot: Bot | None = None,
    runtime: MenuRuntimeContext | None = None,
    new_message: bool = False,
) -> Message | bool:
    bot = bot if bot is not None else target.bot
    if bot is None:
        raise ValueError('Target object does not bound to any bot and `bot` was not passed.')

    runtime = extract_runtime(target) if runtime is None else runtime
    if runtime.chat_id is None:
        raise ValueError('Chat ID is None.')  # todo

    if new_message:
        return await bot.send_rich_message(
            rich_message=InputRichMessage(html=menu.text),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=menu.keyboard),
            chat_id=runtime.chat_id,
            message_thread_id=runtime.thread_id,
        )
    if runtime.message_id is None:
        raise ValueError('Message ID is None.')

    return await bot.edit_message_text(
        rich_message=InputRichMessage(html=menu.text),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=menu.keyboard),
        chat_id=runtime.chat_id,
        message_id=runtime.message_id,
    )


async def apply_menu_context(
    context: MenuContext,
    target: BotContextController,
    *,
    bot: Bot | None = None,
    ui_registry: UIRegistry | None = None,
    new_message: bool = False,
) -> Message | bool:
    ui_registry = ui_registry if ui_registry is not None else global_ui_registry()
    return await apply_menu(
        menu=await ui_registry.build_menu(menu_context=context),
        target=target,
        bot=bot,
        new_message=new_message,
    )


async def apply_menu_snapshot(
    snapshot: MenuContextSnapshot,
    target: BotContextController,
    *,
    bot: Bot | None = None,
    ui_registry: UIRegistry | None = None,
    new_message: bool = False,
) -> Message | bool:
    ui_registry = ui_registry if ui_registry is not None else global_ui_registry()
    type = ui_registry.get_menu_context_type(snapshot.menu_id)
    context = type.from_snapshot(snapshot, runtime=extract_runtime(target))

    return await apply_menu_context(
        context=context,
        target=target,
        bot=bot,
        ui_registry=ui_registry,
        new_message=new_message,
    )
