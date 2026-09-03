from __future__ import annotations

from html import escape

from hubplatform.i18n import Translator
from hubplatform.telegram.ui import (
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.expressions.registry import ArgDocs, ExpressionsRegistry
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.app.components.telegram.ui.callbacks import OpenMenu
from hubplatform.app.components.telegram.ui.finalizers import StripAndNavigationFinalizer


expressions_ui_registry = UIRegistry()


class ExpressionsListMenuContext(MenuContext):
    category_id: str | None = None
    expand_subcategories: bool = False


class ExpressionDocsMenuContext(MenuContext):
    expression_id: str


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expression_categories_list_menu,
    context_type=MenuContext,
)
async def build_expression_categories_list_menu(
    ctx: MenuBuildContext[MenuContext],
    expressions_registry: ExpressionsRegistry,
    translator: Translator,
) -> MenuBuildingSpec:
    menu_spec = MenuSpec()
    for category_id, category in expressions_registry.categories.items():
        menu_spec.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'open_expressions_list:{category_id}',
                text=translator.translate(category.name),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expressions_list_menu,
                    context=ExpressionsListMenuContext(category_id=category_id).dump(),
                ),
            )
        )

    menu_spec.footer_keyboard.append(
        KeyboardBlockSpec.callback_button(
            block_id='show_expressions',
            text=translator.translate('telegram-ui-expressions-show_expressions_btn'),
            callback_data=OpenMenu(
                menu_id=MenuIDs.expressions.expressions_list_menu,
                context=ExpressionsListMenuContext().dump(),
                move_to_history=False,
            ),
            style='success',
        )
    )

    menu_spec.header_text = (
        f'<h2>{translator.translate("telegram-ui-expressions-menu_title")}</h2>'
    )
    menu_spec.body_text = translator.translate('telegram-ui-expressions-desc')
    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expressions_list_menu,
    context_type=ExpressionsListMenuContext,
)
async def build_expressions_list_menu(
    ctx: MenuBuildContext[ExpressionsListMenuContext],
    expressions_registry: ExpressionsRegistry,
    translator: Translator,
) -> MenuBuildingSpec:
    menu_spec = MenuSpec()
    if ctx.context.category_id is None:
        expressions = expressions_registry.expressions
    else:
        expressions = expressions_registry.get_expressions(
            ctx.context.category_id, expand_subcategories=ctx.context.expand_subcategories
        )

    for expression_id, expression in expressions.items():
        menu_spec.main_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id=f'open_expression_docs:{expression_id}',
                text=translator.translate(expression.name),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expression_docs_menu,
                    context=ExpressionDocsMenuContext(expression_id=expression_id).dump(),
                ),
            )
        )

    if ctx.context.category_id is None:
        menu_spec.footer_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id='show_categories',
                text=translator.translate('telegram-ui-expressions-show_categories_btn'),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expression_categories_list_menu,
                    context=MenuContext().dump(),
                    move_to_history=False,
                ),
                style='success',
            )
        )

    if ctx.context.category_id is not None:
        menu_spec.footer_keyboard.append(
            KeyboardBlockSpec.callback_button(
                block_id='toggle_expand_categories',
                text=translator.translate(
                    'telegram-ui-expressions-show_subcategories_btn'
                    if not ctx.context.expand_subcategories
                    else 'telegram-ui-expressions-hide_subcategories_btn'
                ),
                callback_data=OpenMenu(
                    menu_id=MenuIDs.expressions.expressions_list_menu,
                    context=ExpressionsListMenuContext(
                        category_id=ctx.context.category_id,
                        expand_subcategories=not ctx.context.expand_subcategories,
                    ).dump(),
                    move_to_history=False,
                ),
                style='success' if not ctx.context.expand_subcategories else 'danger',
            )
        )

    menu_spec.header_text = (
        f'<h2>{translator.translate("telegram-ui-expressions-menu_title")}</h2>'
    )
    if ctx.context.category_id is not None:
        category = expressions_registry.categories[ctx.context.category_id]
        menu_spec.header_text += f'<h3>{escape(translator.translate(category.name))}</h3>'
    menu_spec.body_text = translator.translate('telegram-ui-expressions-desc')

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@expressions_ui_registry.add_menu_builder(
    menu_id=MenuIDs.expressions.expression_docs_menu,
    context_type=ExpressionDocsMenuContext,
)
class ExpressionDocsMenuBuilder:
    async def __call__(
        self,
        ctx: MenuBuildContext[ExpressionDocsMenuContext],
        expressions_registry: ExpressionsRegistry,
        translator: Translator,
    ) -> MenuBuildingSpec:
        expression = expressions_registry.expressions[ctx.context.expression_id]
        menu_spec = MenuSpec()
        menu_spec.header_text = translator.translate(
            f'<h2>Выражение <code>${escape(expression.id)}()</code></h2>'
        )
        menu_spec.header_text += f'<h4>{escape(translator.translate(expression.name))}</h4>'

        menu_spec.body_text = translator.translate(expression.description.overview)
        if expression.description.args_doc:
            menu_spec.body_text += (
                f'<hr /><h3>{translator.translate("telegram-ui-expressions-parameters")}</h3>'
            )
            for arg in expression.description.args_doc.values():
                menu_spec.body_text += self.build_arg_doc(arg, translator)

        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    def build_arg_doc(self, arg_doc: ArgDocs, translator: Translator) -> str:
        kinds = {
            'normal': 'telegram-ui-expressions-parameter_kind-normal',
            'positional_only': 'telegram-ui-expressions-parameter_kind-positional_only',
            'keyword_only': 'telegram-ui-expressions-parameter_kind-kw_only',
        }
        kind = kinds.get(arg_doc.kind, arg_doc.kind)
        table = f"""
<tr>
    <th align="center">
        {translator.translate('telegram-ui-expressions-params_table-property')}
    </th>
    <th align="center">
        {translator.translate('telegram-ui-expressions-params_table-value')}
    </th>
</tr>
<tr>
    <td>{translator.translate('telegram-ui-expressions-params_table-name')}</td>
    <td><code>{escape(arg_doc.key)}</code></td>
</tr>
<tr>
    <td>{translator.translate('telegram-ui-expressions-params_table-is_required')}</td>
    <td>
        {
            translator.translate('telegram-ui-expressions-params_table-not_required')
            if arg_doc.default is not None
            else translator.translate('telegram-ui-expressions-params_table-required')
        }
    </td>
</tr>
<tr>
    <td>{translator.translate('telegram-ui-expressions-params_table-kind')}</td>
    <td>{translator.translate(kind)}</td>
</tr>"""
        if isinstance(arg_doc.possible_values, str):
            table += f"""
<tr>
    <td>{translator.translate('telegram-ui-expressions-params_table-possible_values')}</td>
    <td>{arg_doc.possible_values}</td>
</tr>"""
        if arg_doc.default is not None:
            table += f"""
<tr>
    <td>{translator.translate('telegram-ui-expressions-params_table-default')}</td>
    <td><code>{escape(arg_doc.default)}</code></td>
</tr>
"""

        total = f'<table bordered striped>{table}</table>'

        if isinstance(arg_doc.possible_values, dict):
            values_table = f"""
<tr>
    <th align="center">
        {translator.translate('telegram-ui-expressions-possible_values_table-value')}
    </th>
    <th align="center">
        {translator.translate('telegram-ui-expressions-possible_values_table-desc')}
    </th>
</tr>
"""
            values_table += ''.join(
                f'<tr><td><code>{escape(key)}</code></td><td>{translator.translate(desc)}</td></tr>'
                for key, desc in arg_doc.possible_values.items()
            )
            total += (
                f'<hr /><h4>'
                f'{translator.translate("telegram-ui-expressions-params_table-possible_values")}'
                f'</h4>'
                f'<table bordered striped>{values_table}</table>'
            )

        total = f'<i>{arg_doc.overview}</i>\n{total}'
        return (
            f'<details>'
            f'<summary>{arg_doc.name} (<code>{arg_doc.key}</code>)</summary>'
            f'{total}'
            f'</details>'
        )
