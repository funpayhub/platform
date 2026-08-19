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
from hubplatform.telegram.app.ui.finalizers import StripAndNavigationFinalizer
from collections.abc import Sequence

from . import callbacks as cbs


registry = UIRegistry()


BUTTON_BUILDERS: dict[type[Node], CallableWrapper[KeyboardBlockSpec]] = {}


def _get_node_builder(node: Node) -> CallableWrapper[KeyboardBlockSpec] | None:
    for node_type in reversed(list(BUTTON_BUILDERS.keys())):
        if isinstance(node, node_type):
            return BUTTON_BUILDERS[node_type]
    return None


class NodeMenuContext(MenuContext):
    node_path: Sequence[str]


@registry.add_menu_builder(menu_id='hubplatform.pyconfigtree:node', context_type=NodeMenuContext)
async def build_node_menu(
    ctx: NodeMenuContext, properties: Properties, tr: Translator, app_context: Mapping[str, Any]
) -> MenuBuildingSpec:
    node = properties.get_node(path=ctx.node_path)
    menu_spec = MenuSpec()
    for subnode in node.subnodes.values():
        if (builder := _get_node_builder(subnode)) is None:
            menu_spec.main_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='hubplatform.pyconfigtree:unknown_node',
                    text=tr.translate('hubplatform.telegram_ui.pyconfigtree:unknown_node_type'),
                    callback_data=ui_cbs.Dummy(),
                )
            )
            continue
        menu_spec.main_keyboard.append(await builder(args=[subnode, tr, ctx], data=app_context))
    menu_spec.body_text = "<b>sun' hui v chai!"

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


async def properties_button_builder(
    node: Properties, i18n: Translator, menu_ctx: MenuContext
) -> KeyboardBlockSpec:
    ctx = NodeMenuContext(
        menu_id='hubplatform.pyconfigtree:node',
        node_path=node.path,
        ui_history=menu_ctx.as_ui_history()
    )

    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree:properties',
        text=i18n.translate(node.name),
        callback_data=ui_cbs.OpenMenu(snapshot=ctx.snapshot())
    )

BUTTON_BUILDERS[Properties] = CallableWrapper(properties_button_builder)


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
