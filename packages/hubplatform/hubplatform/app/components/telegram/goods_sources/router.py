from __future__ import annotations


__all__ = ['goods_sources_router']

import re

from aiogram import F
from aiogram.types import Message, CallbackQuery as Query, BufferedInputFile
from aiogram.fsm.context import FSMContext

from hubplatform.telegram import Router
from hubplatform.telegram.ui import UIManager, MenuContext
from hubplatform.goods_source import GoodsError, FileGoodsSource, GoodsSourcesManager
from hubplatform.telegram.ui.session import MenuFrame
from hubplatform.app.components.telegram.utils import abort_input, finish_input
from hubplatform.app.components.telegram.menu_ids import MenuIDs

from . import states, builders, callbacks as cbs
from ._internal import (
    parse_goods,
    serialize_goods,
    file_source_path,
    parse_index_ranges,
    remove_goods_by_ranges,
)


goods_sources_router = Router(name='hubplatform.goods_sources')


async def _read_goods(m: Message) -> list[str]:
    if m.bot is None:
        raise ValueError('Bot is not bound to message.')

    bot = m.bot
    if m.document is not None:
        doc = await bot.download(m.document)
        try:
            content = doc.getvalue().decode('utf-8-sig')  # type: ignore [union-attr]  # not None
        except UnicodeDecodeError as error:
            raise ValueError('Файл должен быть сохранён в кодировке UTF-8.') from error
    elif m.text is not None:
        content = m.text
    else:
        raise ValueError('Отправьте текстовое сообщение или UTF-8 файл.')

    goods = parse_goods(content)
    if not goods:
        raise ValueError('Не найдено ни одного товара. Отправьте хотя бы одну строку.')
    return goods


@goods_sources_router.callback_query(cbs.StartFileSourceCreation.filter())
async def start_file_source_creation(
    q: Query,
    cbd: cbs.StartFileSourceCreation,
    ui_manager: UIManager,
    state: FSMContext,
) -> None:
    result = await ui_manager.open_menu(
        menu_id=MenuIDs.goods_sources.file_source_input_menu,
        context=builders.FileSourceInputMenuContext(return_session_id=cbd.session_id),
        environment=q,
    )
    await states.CreatingFileSourceState(
        return_session_id=cbd.session_id, input_session_id=result.session.id
    ).set(state)
    await q.answer()


@goods_sources_router.message(states.CreatingFileSourceState.filter())
async def create_file_source(
    m: Message,
    state: FSMContext,
    ui_manager: UIManager,
    goods_manager: GoodsSourcesManager,
) -> None:
    data = await states.CreatingFileSourceState.get(state)
    if m.text is None or '\n' in m.text or '\r' in m.text:
        await m.answer('Отправьте название источника одним текстовым сообщением.')
        return

    try:
        path = file_source_path(m.text)
        if goods_manager.get(path.as_uri()) is not None:
            raise ValueError('источник с таким названием уже существует.')
        await goods_manager.add_source(FileGoodsSource, path)
    except ValueError as error:
        await m.answer(f'Не удалось создать источник: {error}')
        return
    except OSError as error:
        await m.answer(f'Не удалось создать файл источника: {error}')
        return

    await finish_input(m, state, ui_manager, data.return_session_id, data.input_session_id)


@goods_sources_router.callback_query(cbs.StartGoodsInput.filter())
async def start_goods_input(
    q: Query,
    cbd: cbs.StartGoodsInput,
    ui_manager: UIManager,
    state: FSMContext,
    goods_manager: GoodsSourcesManager,
) -> None:
    if goods_manager.get(cbd.source_id) is None:
        await q.answer('Источник больше не существует.', show_alert=True)
        return

    context = builders.SourceInputMenuContext(
        source_id=cbd.source_id,
        action=cbd.action,
        return_session_id=cbd.session_id,
    )
    result = await ui_manager.open_menu(
        menu_id=MenuIDs.goods_sources.source_input_menu,
        context=context,
        environment=q,
    )

    await states.GoodsActionState(
        source_id=cbd.source_id,
        action=cbd.action,
        return_session_id=cbd.session_id,
        input_session_id=result.session.id,
    ).set(state)
    await q.answer()


@goods_sources_router.message(states.GoodsActionState.filter(F.action == 'add'))
async def add_goods(
    m: Message,
    state: FSMContext,
    ui_manager: UIManager,
    goods_manager: GoodsSourcesManager,
) -> None:
    data = await states.GoodsActionState.get(state)
    if goods_manager.get(data.source_id) is None:
        await abort_input(
            m, state, ui_manager, data.input_session_id, 'Источник больше не существует.'
        )
        return

    try:
        goods = await _read_goods(m)
        await goods_manager.add_goods(data.source_id, goods)
    except (GoodsError, ValueError, OSError) as error:
        await m.answer(str(error))
        return

    await finish_input(m, state, ui_manager, data.return_session_id, data.input_session_id)


@goods_sources_router.message(states.GoodsActionState.filter(F.action == 'replace'))
async def replace_goods(
    m: Message,
    state: FSMContext,
    ui_manager: UIManager,
    goods_manager: GoodsSourcesManager,
) -> None:
    data = await states.GoodsActionState.get(state)
    source = goods_manager.get(data.source_id)
    if source is None:
        await abort_input(
            m, state, ui_manager, data.input_session_id, 'Источник больше не существует.'
        )
        return

    try:
        goods = await _read_goods(m)
        await source.set_goods(goods)
    except (GoodsError, ValueError, OSError) as error:
        await m.answer(str(error))
        return

    await finish_input(m, state, ui_manager, data.return_session_id, data.input_session_id)


@goods_sources_router.message(states.GoodsActionState.filter(F.action == 'remove'))
async def remove_goods(
    m: Message, state: FSMContext, ui_manager: UIManager, goods_manager: GoodsSourcesManager
) -> None:
    data = await states.GoodsActionState.get(state)
    if (source := goods_manager.get(data.source_id)) is None:
        await abort_input(
            m, state, ui_manager, data.input_session_id, 'Источник больше не существует.'
        )
        return
    if m.text is None:
        await m.answer('Отправьте индексы и диапазоны текстовым сообщением.')
        return

    try:
        ranges = parse_index_ranges(m.text)
        removed = await remove_goods_by_ranges(source, ranges)
    except (GoodsError, ValueError, OSError) as error:
        await m.answer(f'Не удалось разобрать индексы: {error} Пример: 20-40, 13, 14, 120-200.')
        return

    if removed == 0:
        await m.answer('Ни один из указанных индексов не существует.')
        return

    await finish_input(m, state, ui_manager, data.return_session_id, data.input_session_id)


def _export_filename(source_name: str) -> str:
    name = re.sub(r'[^\w.-]+', '_', source_name, flags=re.UNICODE).strip('._') or 'goods'
    return name if name.lower().endswith('.txt') else f'{name}.txt'


@goods_sources_router.callback_query(cbs.ExportGoods.filter())
async def export_goods(q: Query, cbd: cbs.ExportGoods, goods_manager: GoodsSourcesManager) -> None:
    source = goods_manager.get(cbd.source_id)
    if source is None:
        await q.answer('Источник больше не существует.', show_alert=True)
        return

    goods = await goods_manager.get_goods(cbd.source_id, -1)
    payload = serialize_goods(goods).encode('utf-8')
    document = BufferedInputFile(
        payload,
        filename=_export_filename(str(source)),
    )

    if isinstance(q.message, Message):
        await q.message.answer_document(
            document=document,
            caption=f'Товары из источника «{str(source)}»: {len(goods)} шт.',
            parse_mode=None,
        )
    elif q.message is not None:
        await q.bot.send_document(  # type: ignore[union-attr]  # not None
            chat_id=q.message.chat.id,
            document=document,
            caption=f'Товары из источника «{str(source)}»: {len(goods)} шт.',
            parse_mode=None,
        )
    await q.answer()


@goods_sources_router.callback_query(cbs.DeleteSource.filter())
async def delete_source(
    q: Query,
    cbd: cbs.DeleteSource,
    ui_manager: UIManager,
    goods_manager: GoodsSourcesManager,
) -> None:
    async with ui_manager.edit_session(session_id=cbd.session_id, trigger=q, rerender=True) as s:
        try:
            await goods_manager.remove_source(cbd.source_id)
            if s.history:
                s.current = s.history.pop()
            else:
                s.current = MenuFrame.from_menu_context(
                    menu_id=MenuIDs.goods_sources.sources_list_menu,
                    menu_context=MenuContext(),
                )
        except (GoodsError, OSError) as error:
            await q.answer(f'Не удалось удалить источник: {error}', show_alert=True)
            return
    await q.answer('Источник удалён.')
