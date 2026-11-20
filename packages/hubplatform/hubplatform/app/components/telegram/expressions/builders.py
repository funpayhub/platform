from __future__ import annotations

from typing import Literal, Annotated
from collections.abc import Mapping, Iterable, Sequence

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
from hubplatform.expressions.traits import Trait
from hubplatform.expressions.manager import (
    ExpressionsScope,
    ExpressionEnvelope,
    ExpressionsManager,
)
from hubplatform.expressions.manager.category import CategoryPath, ExpressionsCategoryNode
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.app.components.telegram.ui.callbacks import OpenMenu
from hubplatform.app.components.telegram.ui.finalizers import StripAndNavigationFinalizer


expressions_ui_registry = UIRegistry()

CATEGORY_EMOJI = '📁'
CONTEXT_EMOJI = '📍'
TRAIT_ON_EMOJI = '✅'
TRAIT_OFF_EMOJI = '▫️'

MENU_TITLE = I18nString('telegram-ui-expressions-menu_title', 'Выражения')
MENU_DESCRIPTION = I18nString(
    'telegram-ui-expressions-desc',
    'Выражения позволяют автоматически подставлять нужные данные в тексты, которые '
    'отправляются пользователям, например в сообщения и ответы на заказы и отзывы',
)
TRAITS_HINT = I18nString(
    'telegram-ui-expressions-traits_hint',
    'Отметьте, какие данные есть в тексте, и в списке останутся только подходящие выражения',
)
CONTEXT_LABEL = I18nString('telegram-ui-expressions-context_label', 'Контекст')
ANY_TEXT = I18nString('telegram-ui-expressions-any_text', 'Любой текст')
ANY_TEXT_DESCRIPTION = I18nString(
    'telegram-ui-expressions-any_text_desc', 'Показаны выражения, которые работают в любом тексте'
)
SELECTED_TRAITS_DESCRIPTION = I18nString(
    'telegram-ui-expressions-selected_traits_desc',
    'Показаны выражения, которые работают в тексте с этими данными',
)
CATEGORY_LABEL = I18nString('telegram-ui-expressions-category_label', 'Категория')
UNCATEGORIZED_BUTTON = I18nString('telegram-ui-expressions-uncategorized_btn', 'Без категории')
SHOW_ALL_BUTTON = I18nString('telegram-ui-expressions-show_all_btn', 'Показать все')
NO_EXPRESSIONS = I18nString('telegram-ui-expressions-no_expressions', 'Здесь нет выражений')
EXPRESSION_NOT_FOUND = I18nString(
    'telegram-ui-expressions-expression_not_found', 'Это выражение больше не существует'
)
EXPRESSION_TITLE = I18nString('telegram-ui-expressions-expression_title', 'Выражение')
REQUIRES = I18nString('telegram-ui-expressions-requires', 'Требует')
AVAILABLE_EVERYWHERE = I18nString(
    'telegram-ui-expressions-available_everywhere', 'Доступно в любом тексте'
)
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


type _View = Literal['browse', 'all', 'uncategorized']


class ExpressionsListMenuContext(MenuContext):
    traits: tuple[str, ...] = ()
    """IDs of the selected traits. The menu shows the expressions available for a container
    with traits of these types. Unknown IDs (for example, of a removed plugin) are ignored."""

    category: tuple[str, ...] = ()
    """Path of the category to open. The empty path is the top level."""

    view: _View = 'browse'
    """`browse` shows the trait filters, subcategories and the expressions of the category,
    `all` shows every expression of the category and its subcategories as a flat list,
    `uncategorized` shows expressions without a category."""


class ExpressionDocsMenuContext(MenuContext):
    traits: tuple[str, ...] = ()
    """IDs of the traits selected in the list the expression was opened from."""

    call_key: str


def _selected_traits(manager: ExpressionsManager, ids: Iterable[str]) -> tuple[str, ...]:
    """Known trait IDs from ``ids``, without duplicates, in the order traits were registered."""
    wanted = set(ids)
    return tuple(i for i in manager.traits if i in wanted)


def _trait_types(manager: ExpressionsManager, ids: Iterable[str]) -> list[type[Trait]]:
    return [manager.traits[i] for i in ids]


def _category_name(node: ExpressionsCategoryNode) -> str:
    if node.info is None:
        return node.id or ''
    return node.info.name


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
        None if node.info is None else node.info.description,
    )


def _context_info_block(trait_types: Sequence[type[Trait]]) -> I18nMultiString:
    if not trait_types:
        return _info_block(CONTEXT_EMOJI, CONTEXT_LABEL, ANY_TEXT, ANY_TEXT_DESCRIPTION)
    names = I18nMultiString(*(i.name for i in trait_types), separator=' + ')
    return _info_block(CONTEXT_EMOJI, CONTEXT_LABEL, names, SELECTED_TRAITS_DESCRIPTION)


def _requirement_text(envelope: ExpressionEnvelope) -> I18nMultiString:
    if envelope.requirement.is_empty:
        return I18nMultiString(AVAILABLE_EVERYWHERE)
    names = I18nMultiString(*(i.name for i in envelope.requirement.traits), separator=' + ')
    return I18nMultiString(REQUIRES, ': ', names)


def _added(scope: ExpressionsScope, base: ExpressionsScope) -> int:
    """How many expressions ``scope`` has that ``base`` does not have or resolves differently."""
    return sum(1 for k, v in scope.expressions.items() if base.expressions.get(k) is not v)


_ByCategory = Mapping[CategoryPath | None, Mapping[str, ExpressionEnvelope]]


def _subtree(node: ExpressionsCategoryNode, by_category: _ByCategory) -> list[ExpressionEnvelope]:
    """Expressions of a category and its subcategories. For the root it is every expression."""
    result = [j for i in node.chain_to_tails for j in by_category.get(i.path, {}).values()]
    if node.is_root:
        result += by_category.get(None, {}).values()
    return result


def _by_call_key(envelopes: Iterable[ExpressionEnvelope]) -> list[ExpressionEnvelope]:
    return sorted(envelopes, key=lambda i: i.call_key)


def _open_list(
    traits: tuple[str, ...],
    category: CategoryPath = (),
    view: _View = 'browse',
    move_to_history: bool = True,
) -> OpenMenu:
    return OpenMenu(
        menu_id=MenuIDs.expressions.expressions_list_menu,
        context=ExpressionsListMenuContext(traits=traits, category=category, view=view).dump(),
        move_to_history=move_to_history,
    )


def _add_trait_toggles(
    menu_spec: MenuSpec,
    manager: ExpressionsManager,
    selected: tuple[str, ...],
    scope: ExpressionsScope,
) -> None:
    """Adds a button for every registered trait that turns it on or off in the filter."""
    for trait_id, trait_type in manager.traits.items():
        is_selected = trait_id in selected
        toggled = _selected_traits(
            manager,
            [i for i in selected if i != trait_id] if is_selected else [*selected, trait_id],
        )
        added = 0
        if not is_selected:
            added = _added(manager.get_scope(_trait_types(manager, toggled)), scope)

        menu_spec.header_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'toggle_trait:{trait_id}',
                text=I18nMultiString(
                    f'{TRAIT_ON_EMOJI if is_selected else TRAIT_OFF_EMOJI} ',
                    trait_type.name,
                    f' (+{added})' if added else '',
                ),
                callback_data=_open_list(toggled, move_to_history=False),
            )
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

    selected = _selected_traits(expr, ctx.context.traits)
    trait_types = _trait_types(expr, selected)
    scope = expr.get_scope(trait_types)
    by_category = scope.expressions_by_category
    category = ctx.context.category
    view = ctx.context.view

    try:
        node: ExpressionsCategoryNode | None = expr.get_category(category)
    except KeyError:
        node = None

    menu_spec.header_text += _context_info_block(trait_types)
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
            menu_spec.body_text += I18nMultiString(
                '<p>', MENU_DESCRIPTION, '</p><p><i>', TRAITS_HINT, '</i></p>'
            )
            _add_trait_toggles(menu_spec, expr, selected, scope)

        for chain in chains:
            name = I18nMultiString(*(_category_name(i) for i in chain), separator=' › ')
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id=f'open_category:{".".join(chain[-1].path)}',
                    text=I18nMultiString(
                        f'{CATEGORY_EMOJI} ', name, f' ({len(_subtree(chain[0], by_category))})'
                    ),
                    callback_data=_open_list(selected, chain[-1].path),
                )
            )

        if not category and uncategorized and chains:
            menu_spec.header_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='open_uncategorized',
                    text=I18nMultiString(
                        f'{CATEGORY_EMOJI} ', UNCATEGORIZED_BUTTON, f' ({len(uncategorized)})'
                    ),
                    callback_data=_open_list(selected, view='uncategorized'),
                )
            )

        if len(subtree) > len(shown):
            menu_spec.footer_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='show_all',
                    text=I18nMultiString(SHOW_ALL_BUTTON, f' ({len(subtree)})'),
                    callback_data=_open_list(selected, category, view='all'),
                    style='success',
                )
            )

    for envelope in shown:
        menu_spec.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'open_expression_docs:{envelope.call_key}',
                text=I18nMultiString(envelope.expression.docs.name, f' (${envelope.call_key})'),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expression_docs_menu,
                    context=ExpressionDocsMenuContext(
                        traits=selected, call_key=envelope.call_key
                    ).dump(),
                ),
            )
        )

    if not shown and not chains:
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

        trait_types = _trait_types(expr, _selected_traits(expr, ctx.context.traits))
        envelope = expr.get_scope(trait_types).expressions.get(call_key)
        if envelope is None:
            menu_spec.body_text = EXPRESSION_NOT_FOUND
            return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

        if envelope.category is not None:
            menu_spec.header_text += _category_info_block(expr.get_category(envelope.category))
        menu_spec.header_text += I18nMultiString('<p><i>', _requirement_text(envelope), '</i></p>')

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
