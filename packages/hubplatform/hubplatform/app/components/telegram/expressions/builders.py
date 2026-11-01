from __future__ import annotations

from typing import Literal
from dataclasses import dataclass
from html import escape
from collections.abc import Mapping, Iterator

from hubplatform.i18n import I18nString, Translator
from hubplatform.telegram.ui import (
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.expressions.docs import ArgDocs
from hubplatform.expressions.manager import (
    ExpressionsScope,
    ExpressionEnvelope,
    ExpressionsManager,
)
from hubplatform.expressions.category import ExpressionsCategoryNode
from hubplatform.expressions.call_context import ExpressionContext
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.app.components.telegram.ui.callbacks import OpenMenu
from hubplatform.app.components.telegram.ui.finalizers import StripAndNavigationFinalizer


expressions_ui_registry = UIRegistry()

CATEGORY_EMOJI = '📁'
SCOPE_EMOJI = '📍'

MENU_TITLE = I18nString('telegram-ui-expressions-menu_title', 'Выражения')
MENU_DESCRIPTION = I18nString(
    'telegram-ui-expressions-desc',
    'Выражения позволяют автоматически подставлять нужные данные в тексты, которые '
    'отправляются пользователям: в сообщения, ответы на заказы, ответы на отзывы и т.д.',
)
CONTEXT_LABEL = I18nString('telegram-ui-expressions-context_label', 'Контекст')
CATEGORY_LABEL = I18nString('telegram-ui-expressions-category_label', 'Категория')
UNCATEGORIZED_BUTTON = I18nString('telegram-ui-expressions-uncategorized_btn', 'Без категории')
SHOW_ALL_BUTTON = I18nString('telegram-ui-expressions-show_all_btn', 'Показать все')
NO_EXPRESSIONS = I18nString('telegram-ui-expressions-no_expressions', 'Здесь нет выражений.')
SCOPE_NOT_FOUND = I18nString(
    'telegram-ui-expressions-scope_not_found', 'Это место больше не существует.'
)
EXPRESSION_NOT_FOUND = I18nString(
    'telegram-ui-expressions-expression_not_found', 'Это выражение больше не существует.'
)
EXPRESSION_TITLE = I18nString('telegram-ui-expressions-expression_title', 'Выражение')
DEFINED_IN = I18nString('telegram-ui-expressions-defined_in', 'Определено в')
COPY_BUTTON = I18nString('telegram-ui-expressions-copy_btn', 'Копировать')
PARAMETERS = I18nString('telegram-ui-expressions-parameters', 'Параметры')

PARAMETER_KINDS = {
    'normal': I18nString(
        'telegram-ui-expressions-parameter_kind-normal', 'По порядку или по имени'
    ),
    'positional_only': I18nString(
        'telegram-ui-expressions-parameter_kind-positional_only', 'Только по порядку'
    ),
    'keyword_only': I18nString(
        'telegram-ui-expressions-parameter_kind-kw_only', 'Только по имени'
    ),
}
PARAMS_TABLE_PROPERTY = I18nString('telegram-ui-expressions-params_table-property', 'Свойство')
PARAMS_TABLE_VALUE = I18nString('telegram-ui-expressions-params_table-value', 'Значение')
PARAMS_TABLE_NAME = I18nString('telegram-ui-expressions-params_table-name', 'Имя')
PARAMS_TABLE_IS_REQUIRED = I18nString(
    'telegram-ui-expressions-params_table-is_required', 'Обязательный'
)
PARAMS_TABLE_REQUIRED = I18nString('telegram-ui-expressions-params_table-required', 'Да')
PARAMS_TABLE_NOT_REQUIRED = I18nString('telegram-ui-expressions-params_table-not_required', 'Нет')
PARAMS_TABLE_KIND = I18nString('telegram-ui-expressions-params_table-kind', 'Как передавать')
PARAMS_TABLE_DEFAULT = I18nString('telegram-ui-expressions-params_table-default', 'По умолчанию')
PARAMS_TABLE_POSSIBLE_VALUES = I18nString(
    'telegram-ui-expressions-params_table-possible_values', 'Возможные значения'
)
POSSIBLE_VALUES_TABLE_VALUE = I18nString(
    'telegram-ui-expressions-possible_values_table-value', 'Значение'
)
POSSIBLE_VALUES_TABLE_DESC = I18nString(
    'telegram-ui-expressions-possible_values_table-desc', 'Описание'
)


class ExpressionsListMenuContext(MenuContext):
    scope_id: str | None = None
    """ID of the context the expressions are shown for. `None` is the root context."""

    category: str | None = None
    """Category to open. `None` is the top level of the scope."""

    view: Literal['browse', 'all', 'uncategorized'] = 'browse'
    """`browse` shows subscopes, subcategories and the expressions of the category,
    `all` shows every expression of the category and its subcategories as a flat list,
    `uncategorized` shows expressions without a category."""


class ExpressionDocsMenuContext(MenuContext):
    scope_id: str | None = None
    call_key: str


def _resolve_scope(manager: ExpressionsManager, scope_id: str | None) -> ExpressionsScope | None:
    try:
        return manager.get(ExpressionContext) if scope_id is None else manager.get_by_id(scope_id)
    except KeyError, ValueError:
        return None


def _scope_title(scope: ExpressionsScope, translator: Translator) -> str:
    return translator.translate(scope.context_type.name)


def _scope_path_title(scope: ExpressionsScope, translator: Translator) -> str:
    chain = reversed(list(scope.chain_to_root))
    return ' › '.join(_scope_title(i, translator) for i in chain)


def _scope_description(scope: ExpressionsScope, translator: Translator) -> str:
    return translator.translate(scope.context_type.description)


def _category_name(node: ExpressionsCategoryNode, translator: Translator) -> str:
    if node.category is None:
        return node.name or ''
    return translator.translate(node.category.name)


def _category_description(node: ExpressionsCategoryNode, translator: Translator) -> str | None:
    return None if node.category is None else translator.translate(node.category.description)


def _info_block(emoji: str, label: str, title: str, description: str | None) -> str:
    block = f'<p>{emoji} <b>{escape(label)}:</b> {escape(title)}</p>'
    if description:
        block += f'<p><i>{escape(description)}</i></p>'
    return block


def _category_path_title(node: ExpressionsCategoryNode, translator: Translator) -> str:
    chain = reversed([i for i in node.chain_to_root if not i.is_root])
    return ' › '.join(_category_name(i, translator) for i in chain)


@dataclass(frozen=True)
class _CategoryFolder:
    chain: tuple[ExpressionsCategoryNode, ...]
    """Categories the folder stands for, from the topmost one. Empty categories with a single
    subcategory are collapsed into the same folder."""

    count: int

    @property
    def target(self) -> ExpressionsCategoryNode:
        return self.chain[-1]


_ByCategory = Mapping[str | None, Mapping[str, ExpressionEnvelope]]


def _subtree(
    node: ExpressionsCategoryNode, by_category: _ByCategory
) -> Iterator[ExpressionEnvelope]:
    """Expressions of a category and its subcategories. For the root it is every expression."""
    yield from by_category.get(node.id, {}).values()
    for subcategory in node.subcategories.values():
        yield from _subtree(subcategory, by_category)


def _folders(node: ExpressionsCategoryNode, by_category: _ByCategory) -> list[_CategoryFolder]:
    """Non-empty subcategories of `node` as folders."""
    folders = []
    for subcategory in node.subcategories.values():
        count = sum(1 for _ in _subtree(subcategory, by_category))
        if not count:
            continue

        chain = [subcategory]
        while not by_category.get(chain[-1].id):
            non_empty = [
                i for i in chain[-1].subcategories.values() if any(_subtree(i, by_category))
            ]
            if len(non_empty) != 1:
                break
            chain.append(non_empty[0])
        folders.append(_CategoryFolder(chain=tuple(chain), count=count))
    return folders


def _by_call_key(envelopes: Iterator[ExpressionEnvelope]) -> list[ExpressionEnvelope]:
    return sorted(envelopes, key=lambda i: i.call_key)


def _open_list(
    scope_id: str | None,
    category: str | None = None,
    view: Literal['browse', 'all', 'uncategorized'] = 'browse',
) -> OpenMenu:
    return OpenMenu(
        menu_id=MenuIDs.expressions.expressions_list_menu,
        context=ExpressionsListMenuContext(scope_id=scope_id, category=category, view=view).dump(),
    )


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expressions_list_menu,
    context_type=ExpressionsListMenuContext,
)
async def build_expressions_list_menu(
    ctx: MenuBuildContext[ExpressionsListMenuContext],
    expressions_manager: ExpressionsManager,
    translator: Translator,
) -> MenuBuildingSpec:
    menu_spec = MenuSpec()
    finalizer = StripAndNavigationFinalizer()
    menu_spec.header_text = f'<h2>{escape(translator.translate(MENU_TITLE))}</h2>'

    scope = _resolve_scope(expressions_manager, ctx.context.scope_id)
    if scope is None:
        menu_spec.body_text = translator.translate(SCOPE_NOT_FOUND)
        return MenuBuildingSpec(menu=menu_spec, finalizer=finalizer)

    by_category = scope.scope_expressions_by_category
    category = ctx.context.category
    view = ctx.context.view
    scope_id = ctx.context.scope_id

    try:
        node: ExpressionsCategoryNode | None = expressions_manager.get_category(category)
    except KeyError:
        node = None

    menu_spec.header_text += _info_block(
        SCOPE_EMOJI,
        translator.translate(CONTEXT_LABEL),
        _scope_path_title(scope, translator),
        _scope_description(scope, translator),
    )
    if node is not None and category is not None:
        menu_spec.header_text += _info_block(
            CATEGORY_EMOJI,
            translator.translate(CATEGORY_LABEL),
            _category_path_title(node, translator),
            _category_description(node, translator),
        )

    folders = _folders(node, by_category) if node is not None else []
    uncategorized = _by_call_key(iter(by_category.get(None, {}).values()))
    subtree = _by_call_key(_subtree(node, by_category)) if node is not None else []
    if view == 'all':
        shown = subtree
    elif view == 'uncategorized':
        shown = uncategorized
    elif category is not None:
        shown = _by_call_key(iter(by_category.get(category, {}).values()))
    else:
        shown = [] if folders else uncategorized

    if view == 'browse':
        if category is None:
            for subscope in scope.populated_subscopes:
                own = len(subscope.scope_expressions)
                title = _scope_title(subscope, translator)
                menu_spec.header_keyboard.append(
                    KeyboardBlockSpec.callback_button(
                        block_id=f'open_scope:{subscope.id}',
                        text=f'{SCOPE_EMOJI} {title}' + (f' ({own})' if own else ''),
                        callback_data=_open_list(subscope.id),
                    )
                )

        for folder in folders:
            label = ' › '.join(_category_name(i, translator) for i in folder.chain)
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id=f'open_category:{folder.target.id}',
                    text=f'{CATEGORY_EMOJI} {label} ({folder.count})',
                    callback_data=_open_list(scope_id, folder.target.id),
                )
            )

        if category is None and uncategorized and folders:
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='open_uncategorized',
                    text=f'{CATEGORY_EMOJI} {translator.translate(UNCATEGORIZED_BUTTON)} '
                    f'({len(uncategorized)})',
                    callback_data=_open_list(scope_id, view='uncategorized'),
                )
            )

        if len(subtree) > len(shown):
            menu_spec.footer_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='show_all',
                    text=f'{translator.translate(SHOW_ALL_BUTTON)} ({len(subtree)})',
                    callback_data=_open_list(scope_id, category, view='all'),
                    style='success',
                )
            )

        if category is None and scope.is_root:
            menu_spec.body_text = f'<p>{escape(translator.translate(MENU_DESCRIPTION))}</p>'

    for envelope in shown:
        name = translator.translate(envelope.expression.docs.name)
        menu_spec.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'open_expression_docs:{envelope.call_key}',
                text=f'{name} (${envelope.call_key})',
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expression_docs_menu,
                    context=ExpressionDocsMenuContext(
                        scope_id=scope_id, call_key=envelope.call_key
                    ).dump(),
                ),
            )
        )

    if not shown and not menu_spec.header_keyboard:
        menu_spec.body_text += f'<p>{escape(translator.translate(NO_EXPRESSIONS))}</p>'

    return MenuBuildingSpec(menu=menu_spec, finalizer=finalizer)


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expression_docs_menu,
    context_type=ExpressionDocsMenuContext,
)
class ExpressionDocsMenuBuilder:
    async def __call__(
        self,
        ctx: MenuBuildContext[ExpressionDocsMenuContext],
        expressions_manager: ExpressionsManager,
        translator: Translator,
    ) -> MenuBuildingSpec:
        menu_spec = MenuSpec()
        call_key = ctx.context.call_key
        menu_spec.header_text = (
            f'<h2>{escape(translator.translate(EXPRESSION_TITLE))} '
            f'<code>${escape(call_key)}</code></h2>'
        )

        scope = _resolve_scope(expressions_manager, ctx.context.scope_id)
        envelope = scope.available_expressions.get(call_key) if scope is not None else None
        if scope is None or envelope is None:
            menu_spec.body_text = translator.translate(EXPRESSION_NOT_FOUND)
            return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

        if envelope.category is not None:
            category_node = expressions_manager.get_category(envelope.category)
            menu_spec.header_text += _info_block(
                CATEGORY_EMOJI,
                translator.translate(CATEGORY_LABEL),
                _category_path_title(category_node, translator),
                _category_description(category_node, translator),
            )

        defined_in = next(i for i in scope.chain_to_root if call_key in i.scope_expressions)
        menu_spec.header_text += (
            f'<p><i>{escape(translator.translate(DEFINED_IN))}: '
            f'{escape(_scope_title(defined_in, translator))}</i></p>'
        )

        docs = envelope.expression.docs
        menu_spec.body_text = escape(translator.translate(docs.overview))
        if docs.arg_docs:
            menu_spec.body_text += f'<hr /><h3>{escape(translator.translate(PARAMETERS))}</h3>'
            for arg in docs.arg_docs.values():
                menu_spec.body_text += self.build_arg_doc(arg, translator)

        menu_spec.footer_keyboard.append(
            KeyboardBlockSpec.copy_text_button(
                block_id='copy_call',
                text=f'{translator.translate(COPY_BUTTON)} ${call_key}',
                copy_text=f'${call_key}',
                style='success',
            )
        )
        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    def build_arg_doc(self, arg_doc: ArgDocs, translator: Translator) -> str:
        def tr(text: str) -> str:
            return escape(translator.translate(text))

        required = (
            PARAMS_TABLE_NOT_REQUIRED if arg_doc.default is not None else PARAMS_TABLE_REQUIRED
        )
        table = f"""
<tr>
    <th align="center">{tr(PARAMS_TABLE_PROPERTY)}</th>
    <th align="center">{tr(PARAMS_TABLE_VALUE)}</th>
</tr>
<tr>
    <td>{tr(PARAMS_TABLE_NAME)}</td>
    <td><code>{escape(arg_doc.key)}</code></td>
</tr>
<tr>
    <td>{tr(PARAMS_TABLE_IS_REQUIRED)}</td>
    <td>{tr(required)}</td>
</tr>
<tr>
    <td>{tr(PARAMS_TABLE_KIND)}</td>
    <td>{tr(PARAMETER_KINDS.get(arg_doc.kind, arg_doc.kind))}</td>
</tr>"""
        if isinstance(arg_doc.possible_values, str):
            table += f"""
<tr>
    <td>{tr(PARAMS_TABLE_POSSIBLE_VALUES)}</td>
    <td>{tr(arg_doc.possible_values)}</td>
</tr>"""
        if arg_doc.default is not None:
            table += f"""
<tr>
    <td>{tr(PARAMS_TABLE_DEFAULT)}</td>
    <td><code>{escape(arg_doc.default)}</code></td>
</tr>
"""

        total = f'<table bordered striped>{table}</table>'

        if isinstance(arg_doc.possible_values, Mapping):
            values_table = f"""
<tr>
    <th align="center">{tr(POSSIBLE_VALUES_TABLE_VALUE)}</th>
    <th align="center">{tr(POSSIBLE_VALUES_TABLE_DESC)}</th>
</tr>
"""
            values_table += ''.join(
                f'<tr><td><code>{escape(key)}</code></td><td>{tr(desc)}</td></tr>'
                for key, desc in arg_doc.possible_values.items()
            )
            total += (
                f'<hr /><h4>{tr(PARAMS_TABLE_POSSIBLE_VALUES)}</h4>'
                f'<table bordered striped>{values_table}</table>'
            )

        total = f'<i>{tr(arg_doc.overview)}</i>\n{total}'
        return (
            f'<details>'
            f'<summary>{tr(arg_doc.name)} (<code>{escape(arg_doc.key)}</code>)</summary>'
            f'{total}'
            f'</details>'
        )
