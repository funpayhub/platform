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
from hubplatform.app.components.telegram.menu_ids import MenuIDs

from .widgets import cancel_button
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
    menu_spec.body_text = translator.translate('telegram-ui-basic-enter_new_page_number')
    menu_spec.footer_keyboard.append(
        KeyboardBlockSpec.prerendered_block(
            block_id='hubplatform.clear_state',
            block=cancel_button(open_session_id=None, translator=translator),
        )
    )

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())
