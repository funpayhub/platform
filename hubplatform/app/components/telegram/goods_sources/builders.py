from __future__ import annotations


__all__ = [
    'SourceInputMenuContext',
    'FileSourceInputMenuContext',
    'SourceMenuContext',
    'goods_sources_ui_registry',
]

from typing import Literal
from html import escape
from math import ceil

from hubplatform.i18n import Translator
from hubplatform.telegram.ui import (
    Button,
    Keyboard,
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.goods_source import GoodsSourcesManager
from hubplatform.app.components.telegram.ui import callbacks as ui_cbs
from hubplatform.telegram.callback_data.hash import HashService
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.app.components.telegram.ui.widgets import (
    cancel_button,
    confirmable_button,
    text_navigation_buttons,
)
from hubplatform.app.components.telegram.ui.finalizers import StripAndNavigationFinalizer

from . import callbacks as cbs


GOODS_PER_PAGE = 10

goods_sources_ui_registry = UIRegistry()


class SourceMenuContext(MenuContext):
    source_id: str


class FileSourceInputMenuContext(MenuContext):
    return_session_id: str


class SourceInputMenuContext(MenuContext):
    source_id: str
    action: Literal['add', 'remove', 'replace']
    return_session_id: str


def _short_button_title(value: str, limit: int = 52) -> str:
    return value if len(value) <= limit else value[: limit - 3] + '...'


@goods_sources_ui_registry.add_menu_builder(
    menu_id=MenuIDs.goods_sources.sources_list_menu,
    context_type=MenuContext,
)
async def build_sources_list_menu(
    ctx: MenuBuildContext[MenuContext], goods_manager: GoodsSourcesManager, translator: Translator
) -> MenuBuildingSpec:
    menu = MenuSpec()

    for index, source in enumerate(list(goods_manager.values())):
        menu.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'hubplatform.goods_sources.open_source.{index}',
                text=escape(f'{_short_button_title(str(source))} · {await source.len()}'),
                callback_data=ui_cbs.OpenMenu(
                    menu_id=MenuIDs.goods_sources.source_menu,
                    context=SourceMenuContext(source_id=source.source_id).dump(),
                ),
            )
        )

    menu.footer_keyboard.append(
        KeyboardBlockSpec.callback_button(
            block_id='hubplatform.goods_sources.add_file_source',
            text=translator.translate('telegram-ui-goods_sources-add_file_source'),
            callback_data=cbs.StartFileSourceCreation(),
            style='success',
        )
    )

    menu.header_text = f'<h2>{translator.translate("telegram-ui-goods_sources-list-title")}</h2>'
    if goods_manager:
        menu.body_text = f"""
<p>
    {translator.translate('telegram-ui-goods_sources-sources_connected')}: 
    <b>{len(goods_manager)}</b>.
</p>
<i>{translator.translate('telegram-ui-goods_sources-select_source_to_control_it')}</i>"""
    else:
        menu.body_text = translator.translate('telegram-ui-goods_sources-no_goods_sources')

    return MenuBuildingSpec(menu=menu, finalizer=StripAndNavigationFinalizer())


@goods_sources_ui_registry.add_menu_builder(
    menu_id=MenuIDs.goods_sources.source_menu,
    context_type=SourceMenuContext,
)
class SourceMenuBuilder:
    async def __call__(
        self,
        ctx: MenuBuildContext[SourceMenuContext],
        goods_manager: GoodsSourcesManager,
        hash_service: HashService,
    ) -> MenuBuildingSpec:
        source = goods_manager.get(ctx.context.source_id)
        menu = MenuSpec()
        menu.header_text = f'<h2>Источник товаров <code>{escape(str(source))}</code></h2>'

        if source is None:
            menu.body_text = '<p>Источник больше не существует.</p>'
            return MenuBuildingSpec(menu=menu, finalizer=StripAndNavigationFinalizer())

        amount = await source.len()
        menu.body_text = (
            '<table bordered striped compact>'
            '<tr><th>Свойство</th><th>Значение</th></tr>'
            f'<tr><td>Название</td><td><code>{escape(str(source))}</code></td></tr>'
            f'<tr><td>Тип</td><td>{escape(type(source).__name__)}</td></tr>'
            f'<tr><td>Товаров</td><td>{amount}</td></tr>'
            f'<tr><td>ID</td><td><code>{escape(source.source_id)}</code></td></tr>'
            '</table>'
            '<hr/>'
        )

        page = ctx.view_state.text_page.get('goods_table', 0)
        pages = max(1, ceil(amount / GOODS_PER_PAGE))
        start = page * GOODS_PER_PAGE
        goods = await source.get_goods(GOODS_PER_PAGE, start=start)
        rows = ['<tr><th>№</th><th>Товар</th></tr>']
        if not goods:
            menu.body_text += '<h3><b>Товаров нет :(</b></h3>'
        else:
            for ind, product in enumerate(goods, start=start + 1):
                preview = product if len(product) <= 200 else product[:197] + '...'
                rows.append(
                    f'<tr><td align="right">{ind}</td><td><code>{escape(preview)}</code></td></tr>'
                )
            menu.body_text += (
                f'<h3>Товары {start + 1}–{start + len(goods)}</h3>'
                f'<table bordered striped compact>{"".join(rows)}</table>'
            )

        buttons = text_navigation_buttons(id='goods_table', max_pages=pages, current_page=page)
        menu.body_text += (
            f'<tg-button-row>{"".join(i.to_html(hash_service) for i in buttons)}</tg-button-row>'
        )

        menu.footer_keyboard.append(
            KeyboardBlockSpec.prerendered_block(
                'hubplatform.goods_sources.source_actions',
                block=self._source_actions(ctx.context),
            ),
        )
        return MenuBuildingSpec(menu=menu, finalizer=StripAndNavigationFinalizer())

    def _source_actions(self, ctx: SourceMenuContext) -> Keyboard:
        return [
            [
                Button(
                    button_id='add_goods',
                    text='＋ Добавить',
                    callback_data=cbs.StartGoodsInput(source_id=ctx.source_id, action='add'),
                    style='success',
                ),
                Button(
                    button_id='remove_goods',
                    text='− Удалить',
                    callback_data=cbs.StartGoodsInput(source_id=ctx.source_id, action='remove'),
                    style='danger',
                ),
            ],
            [
                Button(
                    button_id='export_goods',
                    text='↧ Выгрузить',
                    callback_data=cbs.ExportGoods(source_id=ctx.source_id),
                ),
                Button(
                    button_id='replace_goods',
                    text='↥ Заменить',
                    callback_data=cbs.StartGoodsInput(source_id=ctx.source_id, action='replace'),
                    style='primary',
                ),
            ],
            confirmable_button(
                id='delete_source',
                ctx=ctx,
                text='Удалить источник',
                callback_data=cbs.DeleteSource(source_id=ctx.source_id),
                style='danger',
            ),
        ]


@goods_sources_ui_registry.add_menu_builder(
    menu_id=MenuIDs.goods_sources.file_source_input_menu,
    context_type=FileSourceInputMenuContext,
)
async def build_file_source_input_menu(
    ctx: MenuBuildContext[FileSourceInputMenuContext],
) -> MenuSpec:
    menu = MenuSpec()
    menu.header_text = '<h2>Новый FileSource</h2>'
    menu.body_text = (
        '<p>Отправьте название источника одним сообщением.</p>'
        '<p>Файл будет создан в каталоге <code>storage/goods</code>. '
        'Если расширение не указано, будет добавлено <code>.txt</code>.</p>'
    )
    menu.footer_text = '<i>Название не должно содержать путь.</i>'
    menu.footer_keyboard.append(
        KeyboardBlockSpec.prerendered_block(
            block_id='hubplatform.goods_sources.cancel_file_source_input',
            block=cancel_button(open_session_id=ctx.context.return_session_id),
        )
    )
    return menu


_ACTION_TITLES = {
    'add': 'Добавление товаров',
    'remove': 'Удаление товаров',
    'replace': 'Замена товаров',
}


@goods_sources_ui_registry.add_menu_builder(
    menu_id=MenuIDs.goods_sources.source_input_menu,
    context_type=SourceInputMenuContext,
)
async def build_source_input_menu(
    ctx: MenuBuildContext[SourceInputMenuContext],
) -> MenuSpec:
    menu = MenuSpec()
    menu.header_text = f'<h2>{_ACTION_TITLES[ctx.context.action]}</h2>'

    if ctx.context.action == 'remove':
        menu.body_text = (
            '<p>Отправьте номера товаров и диапазоны одним сообщением.</p>'
            '<p>Например: <code>20-40, 13, 14, 120-200</code>.</p>'
            '<i>Нумерация соответствует первому столбцу таблицы. '
            'Пересекающиеся диапазоны будут объединены.</i>'
        )
    else:
        action = (
            'добавлены в конец источника'
            if ctx.context.action == 'add'
            else 'запишутся вместо всех текущих товаров'
        )
        menu.body_text = (
            '<p>Отправьте товары сообщением или UTF-8 файлом. '
            f'Полученные товары {action}.</p>'
            '<p>Одна строка — один товар. Чтобы добавить перенос строки внутрь товара, '
            'используйте <code>\\n</code>.</p>'
        )

    menu.footer_keyboard.append(
        KeyboardBlockSpec.prerendered_block(
            'hubplatform.goods_sources.cancel_source_input',
            block=cancel_button(open_session_id=ctx.context.return_session_id),
        )
    )
    return menu
