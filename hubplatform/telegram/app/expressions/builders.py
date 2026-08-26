from __future__ import annotations

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
from hubplatform.telegram.app.menu_ids import MenuIDs
from hubplatform.telegram.app.ui.callbacks import OpenMenu
from hubplatform.telegram.app.ui.finalizers import StripAndNavigationFinalizer


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
):
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
            text=translator.translate('Показать выражения'),
            callback_data=OpenMenu(
                menu_id=MenuIDs.expressions.expressions_list_menu,
                context=ExpressionsListMenuContext().dump(),
                move_to_history=False,
            ),
            style='success',
        )
    )

    menu_spec.header_text = translator.translate('<h2>Выражения</h2>')
    menu_spec.body_text = translator.translate(
        'Выражения позволяют автоматически подставлять нужные данные в тексты, которые '
        'отправляются пользователям: в сообщения, ответы на заказы, ответы на отзывы и т.д.'
    )
    return menu_spec


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
                text=translator.translate('Показать категории'),
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
                    'Показать подкатегории'
                    if not ctx.context.expand_subcategories
                    else 'Скрыть подкатегории'
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

    menu_spec.header_text = translator.translate('<h2>Выражения</h2>')
    if ctx.context.category_id is not None:
        category = expressions_registry.categories[ctx.context.category_id]
        menu_spec.header_text += f'<h3>{translator.translate(category.name)}</h3>'

    menu_spec.body_text = translator.translate(
        'Выражения позволяют автоматически подставлять нужные данные в тексты, которые '
        'отправляются пользователям: в сообщения, ответы на заказы, ответы на отзывы и т.д.'
    )

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
    ):
        expression = expressions_registry.expressions[ctx.context.expression_id]
        menu_spec = MenuSpec()
        menu_spec.header_text = translator.translate(
            f'<h2>Выражение <code>${expression.id}()</code></h2>'
        )
        menu_spec.header_text += translator.translate(f'<h4>{expression.name}</h4>')

        menu_spec.body_text = translator.translate(expression.description.overview)
        for arg in expression.description.args_doc.values():
            menu_spec.body_text += self.build_arg_doc(arg, translator)

        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    def build_arg_doc(self, arg_doc: ArgDocs, translator: Translator):
        kinds = {
            'normal': 'По порядку или по имени',
            'positional_only': 'Только по порядку',
            'keyword_only': 'Только по имени',
        }
        kind = kinds.get(arg_doc.kind, translator.translate(arg_doc.kind))
        rows = [
            f'<tr><td>Имя</td><td>{arg_doc.key}</td></tr>',
            f'<tr><td>Обязательный</td><td>{"Нет" if arg_doc.default is not None else "Да"}</td></tr>',
            f'<tr><td>Как передавать</td><td>{kind}</td></tr>',
        ]
        if isinstance(arg_doc.possible_values, str):
            rows.append(
                f'<tr><td>Возможные значения</td><td>{arg_doc.possible_values}</td></tr>',
            )
        if arg_doc.default is not None:
            rows.append(f'<tr><td>По умолчанию</td><td>{arg_doc.default}</td></tr>')

        total = f'<table bordered striped>{"".join(rows)}</table>'

        if isinstance(arg_doc.possible_values, dict):
            rows = [
                f'<tr><td><code>{key}</code></td><td>{desc}</td></tr>'
                for key, desc in arg_doc.possible_values.items()
            ]
            table = f'<table bordered striped>{"".join(rows)}</table>'
            total += f'<hr /><h4>Параметры</h4>{table}'

        total = f'<i>{arg_doc.overview}</i>\n{total}'
        return f'<details><summary>{arg_doc.name}</summary>{total}</details>'
