from __future__ import annotations

from typing import Literal, Annotated
from collections.abc import Mapping, Iterable

from eventry.asyncio.config import FromContext

from hubplatform.i18n import I18nString, I18nMultiString
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
from hubplatform.expressions.category import CategoryPath
from hubplatform.expressions.call_context import ExpressionContext
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.expressions.manager.category_node import ExpressionsCategoryNode
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

    category: tuple[str, ...] = ()
    """Path of the category to open. The empty path is the top level of the scope."""

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


def _category_name(node: ExpressionsCategoryNode) -> str:
    if node.category is None:
        return node.id or ''
    return node.category.name


def _info_block(emoji: str, label: str, title: str, description: str | None) -> I18nMultiString:
    block = I18nMultiString('<p>', emoji, ' <b>', label, ':</b> ', title, '</p>')
    if description:
        block += I18nMultiString('<p><i>', description, '</i></p>')
    return block


def _category_info_block(node: ExpressionsCategoryNode) -> I18nMultiString:
    chain = reversed([i for i in node.chain_to_root if not i.is_root])
    return _info_block(
        CATEGORY_EMOJI,
        CATEGORY_LABEL,
        I18nMultiString(*(_category_name(i) for i in chain), separator=' › '),
        None if node.category is None else node.category.description,
    )


_ByCategory = Mapping[CategoryPath | None, Mapping[str, ExpressionEnvelope]]


def _subtree(node: ExpressionsCategoryNode, by_category: _ByCategory) -> list[ExpressionEnvelope]:
    """Expressions of a category and its subcategories. For the root it is every expression."""
    result = [j for i in node.subtree for j in by_category.get(i.path, {}).values()]
    if node.is_root:
        result += by_category.get(None, {}).values()
    return result


def _by_call_key(envelopes: Iterable[ExpressionEnvelope]) -> list[ExpressionEnvelope]:
    return sorted(envelopes, key=lambda i: i.call_key)


def _open_list(
    scope_id: str | None,
    category: CategoryPath = (),
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
    expr: Annotated[ExpressionsManager, FromContext('expressions_manager')],
) -> MenuBuildingSpec:
    menu_spec = MenuSpec(header_text=I18nMultiString('<h2>', MENU_TITLE, '</h2>'))

    scope = _resolve_scope(expr, ctx.context.scope_id)
    if scope is None:
        menu_spec.body_text = SCOPE_NOT_FOUND
        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    by_category = scope.scope_expressions_by_category
    category = ctx.context.category
    view = ctx.context.view
    scope_id = ctx.context.scope_id

    try:
        node: ExpressionsCategoryNode | None = expr.get_category(category)
    except KeyError:
        node = None

    scope_chain = reversed(list(scope.chain_to_root))
    menu_spec.header_text += _info_block(
        SCOPE_EMOJI,
        CONTEXT_LABEL,
        I18nMultiString(*(i.context_type.name for i in scope_chain), separator=' › '),
        scope.context_type.description,
    )
    if node is not None and category:
        menu_spec.header_text += _category_info_block(node)

    chains = node.subcategory_chains(by_category) if node is not None else []
    uncategorized = _by_call_key(by_category.get(None, {}).values())
    subtree = _by_call_key(_subtree(node, by_category)) if node is not None else []
    if view == 'all':
        shown = subtree
    elif view == 'uncategorized':
        shown = uncategorized
    elif category:
        shown = _by_call_key(by_category.get(category, {}).values())
    else:
        shown = [] if chains else uncategorized

    if view == 'browse':
        if not category:
            for subscope in scope.populated_subscopes:
                own = len(subscope.scope_expressions)
                menu_spec.header_keyboard.append(
                    KeyboardBlockSpec.callback_button(
                        block_id=f'open_scope:{subscope.id}',
                        text=I18nMultiString(
                            f'{SCOPE_EMOJI} ',
                            subscope.context_type.name,
                            f' ({own})' if own else '',
                        ),
                        callback_data=_open_list(subscope.id),
                    )
                )

        for chain in chains:
            name = I18nMultiString(*(_category_name(i) for i in chain), separator=' › ')
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id=f'open_category:{".".join(chain[-1].path)}',
                    text=I18nMultiString(
                        f'{CATEGORY_EMOJI} ', name, f' ({len(_subtree(chain[0], by_category))})'
                    ),
                    callback_data=_open_list(scope_id, chain[-1].path),
                )
            )

        if not category and uncategorized and chains:
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='open_uncategorized',
                    text=I18nMultiString(
                        f'{CATEGORY_EMOJI} ', UNCATEGORIZED_BUTTON, f' ({len(uncategorized)})'
                    ),
                    callback_data=_open_list(scope_id, view='uncategorized'),
                )
            )

        if len(subtree) > len(shown):
            menu_spec.footer_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='show_all',
                    text=I18nMultiString(SHOW_ALL_BUTTON, f' ({len(subtree)})'),
                    callback_data=_open_list(scope_id, category, view='all'),
                    style='success',
                )
            )

        if not category and scope.is_root:
            menu_spec.body_text += I18nMultiString('<p>', MENU_DESCRIPTION, '</p>')

    for envelope in shown:
        menu_spec.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'open_expression_docs:{envelope.call_key}',
                text=I18nMultiString(envelope.expression.docs.name, f' (${envelope.call_key})'),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expression_docs_menu,
                    context=ExpressionDocsMenuContext(
                        scope_id=scope_id, call_key=envelope.call_key
                    ).dump(),
                ),
            )
        )

    if not shown and not menu_spec.header_keyboard:
        menu_spec.body_text += I18nMultiString('<p>', NO_EXPRESSIONS, '</p>')

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expression_docs_menu,
    context_type=ExpressionDocsMenuContext,
)
class ExpressionDocsMenuBuilder:
    async def __call__(
        self,
        ctx: MenuBuildContext[ExpressionDocsMenuContext],
        expr: Annotated[ExpressionsManager, FromContext('expressions_manager')],
    ) -> MenuBuildingSpec:
        call_key = ctx.context.call_key
        menu_spec = MenuSpec(
            header_text=I18nMultiString(
                '<h2>', EXPRESSION_TITLE, f' <code>${call_key}</code></h2>'
            )
        )

        scope = _resolve_scope(expr, ctx.context.scope_id)
        envelope = scope.available_expressions.get(call_key) if scope is not None else None
        if scope is None or envelope is None:
            menu_spec.body_text = EXPRESSION_NOT_FOUND
            return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

        if envelope.category is not None:
            menu_spec.header_text += _category_info_block(expr.get_category(envelope.category))

        defined_in = next(i for i in scope.chain_to_root if call_key in i.scope_expressions)
        menu_spec.header_text += I18nMultiString(
            '<p><i>', DEFINED_IN, ': ', defined_in.context_type.name, '</i></p>'
        )

        docs = envelope.expression.docs
        menu_spec.body_text = docs.overview
        if docs.arg_docs:
            menu_spec.body_text += I18nMultiString('<hr /><h3>', PARAMETERS, '</h3>')
            for arg in docs.arg_docs.values():
                menu_spec.body_text += self.build_arg_doc(arg)

        menu_spec.footer_keyboard.append(
            KeyboardBlockSpec.copy_text_button(
                block_id='copy_call',
                text=I18nMultiString(COPY_BUTTON, f' ${call_key}'),
                copy_text=f'${call_key}',
                style='success',
            )
        )
        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    def build_arg_doc(self, arg_doc: ArgDocs) -> I18nMultiString:
        rows = [
            (PARAMS_TABLE_NAME, f'<code>{arg_doc.key}</code>'),
            (
                PARAMS_TABLE_IS_REQUIRED,
                PARAMS_TABLE_NOT_REQUIRED
                if arg_doc.default is not None
                else PARAMS_TABLE_REQUIRED,
            ),
            (PARAMS_TABLE_KIND, PARAMETER_KINDS.get(arg_doc.kind, arg_doc.kind)),
        ]
        if isinstance(arg_doc.possible_values, str):
            rows.append((PARAMS_TABLE_POSSIBLE_VALUES, arg_doc.possible_values))
        if arg_doc.default is not None:
            rows.append((PARAMS_TABLE_DEFAULT, f'<code>{arg_doc.default}</code>'))

        result = I18nMultiString(
            '<details><summary>',
            arg_doc.name,
            f' (<code>{arg_doc.key}</code>)</summary><i>',
            arg_doc.overview,
            '</i>\n<table bordered striped><tr><th align="center">',
            PARAMS_TABLE_PROPERTY,
            '</th><th align="center">',
            PARAMS_TABLE_VALUE,
            '</th></tr>',
        )
        for label, value in rows:
            result += I18nMultiString('<tr><td>', label, '</td><td>', value, '</td></tr>')
        result += '</table>'

        if isinstance(arg_doc.possible_values, Mapping):
            result += I18nMultiString(
                '<hr /><h4>',
                PARAMS_TABLE_POSSIBLE_VALUES,
                '</h4><table bordered striped><tr><th align="center">',
                POSSIBLE_VALUES_TABLE_VALUE,
                '</th><th align="center">',
                POSSIBLE_VALUES_TABLE_DESC,
                '</th></tr>',
            )
            for key, desc in arg_doc.possible_values.items():
                result += I18nMultiString(
                    f'<tr><td><code>{key}</code></td><td>', desc, '</td></tr>'
                )
            result += '</table>'

        return result + '</details>'
