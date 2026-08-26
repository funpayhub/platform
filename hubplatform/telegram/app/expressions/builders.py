from __future__ import annotations

from hubplatform.i18n import Translator
from hubplatform.telegram.ui import UIRegistry, MenuContext, MenuBuildContext, MenuBuildingSpec
from hubplatform.expressions.registry import ExpressionsRegistry
from hubplatform.telegram.app.ui_names import TelegramAppUINames


formatters_ui_registry = UIRegistry()


class ExpressionsListMenuContext:
    category: str | None = None
    expand_subcategories: bool = False


@formatters_ui_registry.add_menu_builder(
    menu_id=TelegramAppUINames.expressions.expressions_list_menu,
    context_type=MenuContext,
)
async def build_expressions_list_menu(
    ctx: MenuBuildContext[MenuContext],
    expressions_registry: ExpressionsRegistry,
    translator: Translator,
) -> MenuBuildingSpec:
    pass
