from __future__ import annotations

from typing import Any, TypeVar
from collections.abc import Mapping, Callable, Awaitable

from pyconfigtree import (
    Node,
    Properties,
    IntParameter,
    BoolParameter,
    ListParameter,
    FloatParameter,
    StringParameter,
)
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.i18n.base import Translator
from hubplatform.telegram.ui import (
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.telegram.app.ui import callbacks as ui_cbs
from hubplatform.telegram.app.ui_names import TelegramAppUINames, TelegramAppUINames as ui_names
from hubplatform.telegram.app.ui.finalizers import StripAndNavigationFinalizer

from . import callbacks as cbs


properties_ui_registry = UIRegistry()


BUTTON_BUILDERS: dict[type[Node], CallableWrapper[KeyboardBlockSpec]] = {}

_N = TypeVar('_N', bound=Node, default=Any, contravariant=True)
_C = TypeVar('_C', bound=MenuBuildContext, default=Any, contravariant=True)
ButtonBuilderType = Callable[[_N, Translator, _C], Awaitable[KeyboardBlockSpec]]


def _get_node_builder(node: Node) -> CallableWrapper[KeyboardBlockSpec] | None:
    for node_type in reversed(list(BUTTON_BUILDERS.keys())):
        if isinstance(node, node_type):
            return BUTTON_BUILDERS[node_type]
    return None


def register_node_button_builder[T: ButtonBuilderType](for_type: type[Node]) -> Callable[[T], T]:
    def inner(builder: T) -> T:
        BUTTON_BUILDERS[for_type] = CallableWrapper(builder)
        return builder

    return inner


class NodeMenuContext(MenuContext):
    node_path: list[str]


class ListNodeMenuContext(NodeMenuContext): ...


class ManualValueInputContext(NodeMenuContext):
    open_next_session_id: str


@properties_ui_registry.add_menu_builder(
    menu_id=ui_names.properties.properties_menu, context_type=NodeMenuContext
)
async def properties_menu_builder(
    ctx: MenuBuildContext[NodeMenuContext],
    properties: Properties,
    tr: Translator,
    app_context: Mapping[str, Any],
) -> MenuBuildingSpec:
    node = properties.get_node(path=ctx.context.node_path)
    menu_spec = MenuSpec()
    for subnode in node.subnodes.values():
        if (builder := _get_node_builder(subnode)) is None:
            menu_spec.main_keyboard.append(
                KeyboardBlockSpec.callback_button(
                    block_id='hubplatform.pyconfigtree.unknown_node',
                    text=tr.translate('hubplatform-telegram_ui-pyconfigtree-unknown_node_type'),
                    callback_data=ui_cbs.Dummy(),
                )
            )
            continue
        menu_spec.main_keyboard.append(await builder(args=[subnode, tr, ctx], data=app_context))
    menu_spec.body_text = 'Properties node'

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@properties_ui_registry.add_menu_builder(
    menu_id=ui_names.properties.list_param_menu, context_type=ListNodeMenuContext
)
class ListParamMenuBuilder:
    async def __call__(
        self,
        ctx: MenuBuildContext[ListNodeMenuContext],
        properties: Properties,
        tr: Translator,
        app_context: Mapping[str, Any],
    ) -> MenuBuildingSpec:
        node = properties.get_parameter(ctx.context.node_path)
        menu_spec = MenuSpec()
        if not isinstance(node, ListParameter):
            raise TypeError('Cannot build list param menu for not a ListParameter.')
        for index, val in enumerate(node.value):
            menu_spec.main_keyboard.append(
                KeyboardBlockSpec.copy_text_button(
                    block_id=f'hubplatform.pyconfigtree.list_param.item.{index}',
                    text=str(val),
                    copy_text=str(val),
                )
            )

        menu_spec.body_text = 'List param'
        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@properties_ui_registry.add_menu_builder(
    menu_id=ui_names.properties.value_manual_input_menu, context_type=ManualValueInputContext
)
async def build_value_manual_input_menu(
    ctx: MenuBuildContext[ManualValueInputContext],
    properties: Properties,
    translator: Translator,
) -> MenuBuildingSpec:
    menu_spec = MenuSpec()
    entry = properties.get_parameter(ctx.context.node_path)
    menu_spec.body_text = translator.translate('edit-parameter-value-text')

    menu_spec.footer_keyboard.append(
        KeyboardBlockSpec.callback_button(
            block_id='hubplatform.clear_state',
            text=translator.translate('cancel'),
            callback_data=ui_cbs.ClearState(open_session_id=ctx.context.open_next_session_id),
        )
    )

    return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())


@register_node_button_builder(Properties)
async def properties_button_builder(
    node: Properties, i18n: Translator, menu_ctx: MenuBuildContext
) -> KeyboardBlockSpec:
    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree:properties',
        text=i18n.translate(node.name),
        callback_data=ui_cbs.OpenMenu(
            menu_id=TelegramAppUINames.properties.properties_menu,
            context=NodeMenuContext(node_path=list(node.path)).dump(),
        ),
    )


@register_node_button_builder(BoolParameter)
async def toggle_button_builder(
    node: BoolParameter,
    i18n: Translator,
    menu_ctx: MenuBuildContext,
) -> KeyboardBlockSpec:
    prefix = {True: '🟢 ', False: '🔴 '}

    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree:bool_param',
        text=f'{prefix[node.value]}{i18n.translate(node.name)}',
        callback_data=cbs.NextValue(node_path=list(node.path)),
    )


_ids = {
    IntParameter: 'int_param',
    FloatParameter: 'float_param',
    StringParameter: 'string_param',
}


@register_node_button_builder(IntParameter)
@register_node_button_builder(FloatParameter)
@register_node_button_builder(StringParameter)
async def manual_input_parameter_button_builder(
    node: IntParameter | FloatParameter | StringParameter,
    i18n: Translator,
    ctx: MenuBuildContext,
) -> KeyboardBlockSpec:
    for t, block_id in _ids.items():
        if isinstance(node, t):
            break
    else:
        raise ValueError('Unsupported node type.')

    return KeyboardBlockSpec.callback_button(
        block_id=f'hubplatform.pyconfigtree.{block_id}',
        text=i18n.translate(node.name),
        callback_data=cbs.ManualValueInput(node_path=list(node.path)),
    )


@register_node_button_builder(ListParameter)
async def list_parameter_button_builder(
    node: ListParameter[Any],
    i18n: Translator,
    menu_ctx: MenuBuildContext,
) -> KeyboardBlockSpec:
    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree.list_param',
        text=i18n.translate(node.name),
        callback_data=ui_cbs.OpenMenu(
            menu_id=TelegramAppUINames.properties.list_param_menu,
            context=NodeMenuContext(node_path=list(node.path)).dump(),
        ),
    )
