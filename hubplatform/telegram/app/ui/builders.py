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
from hubplatform.telegram.app.menu_ids import MenuIDs

from .callbacks import ClearState
from .finalizers import StripAndNavigationFinalizer


basic_ui_registry = UIRegistry()


@basic_ui_registry.add_menu_builder(
    menu_id=MenuIDs.basic_ui.manual_change_page_menu,
    context_type=MenuContext,
)
async def build_value_manual_input_menu(
    ctx: MenuBuildContext[MenuContext],
    translator: Translator,
) -> MenuBuildingSpec:
    menu_spec = MenuSpec()
    menu_spec.body_text = translator.translate('hubplatform-telegram_ui-enter-new-page-number')

    menu_spec.footer_keyboard.append(
        KeyboardBlockSpec.callback_button(
            block_id='hubplatform.clear_state',
            text=translator.translate('cancel'),
            callback_data=ClearState(),
        )
    )

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())
