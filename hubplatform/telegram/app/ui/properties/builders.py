from __future__ import annotations

from typing import Any
from collections.abc import Mapping

from pyconfigtree import Node, Properties, BoolParameter
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.i18n.base import Translator
from hubplatform.telegram.ui import (
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.telegram.app.ui import callbacks as ui_cbs

from . import callbacks as cbs


registry = UIRegistry()


BUTTON_BUILDERS: dict[type[Node], CallableWrapper[KeyboardBlockSpec]] = {}


class NodeMenuContext(MenuContext):
    node_path: list[str]


@registry.add_menu_builder(menu_id='hubplatform.pyconfigtree_node', context_type=NodeMenuContext)
async def build_node_menu(
    ctx: NodeMenuContext, properties: Properties, tr: Translator, app_context: Mapping[str, Any]
) -> MenuBuildingSpec:
    node = properties.get_node(path=ctx.node_path)
    menu_spec = MenuSpec()
    for i in node.subnodes.values():
        if type(i) not in BUTTON_BUILDERS:
            menu_spec.main_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='hubplatform.pyconfigtree:unknown_node',
                    text=tr.translate('hubplatform.telegram_ui.pyconfigtree:unknown_node_type'),
                    callback_data=ui_cbs.Dummy(),
                )
            )
            continue
        builder = BUTTON_BUILDERS[type(i)]
        menu_spec.main_keyboard.append(await builder(args=[i, tr, ctx], data=app_context))

    return MenuBuildingSpec(menu=menu_spec)


async def toggle_button_builder(
    node: BoolParameter, i18n: Translator, menu_ctx: MenuContext
) -> KeyboardBlockSpec:
    prefix = {True: '🟢 ', False: '🔴 '}
    for i in node.flags:
        if isinstance(i, TelegramToggleUIEmojiFlag):
            prefix[True] = i.on_emoji.emoji if i.on_emoji is not None else prefix[True]
            prefix[False] = i.off_emoji.emoji if i.off_emoji else prefix[False]
            break

    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree:bool_param',
        text=f'{prefix[node.value]}{i18n.translate(node.name)}',
        callback_data=cbs.NextValue(node_path=node.path, open_next=menu_ctx.snapshot()),
    )


BUTTON_BUILDERS[BoolParameter] = CallableWrapper(toggle_button_builder)
