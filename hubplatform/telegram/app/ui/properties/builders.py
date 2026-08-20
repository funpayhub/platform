from __future__ import annotations

from typing import Any, TypeVar
from functools import partial
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
    Button,
    Keyboard,
    MenuSpec,
    UIRegistry,
    MenuContext,
    MenuBuildingSpec,
    KeyboardBlockSpec,
)
from hubplatform.telegram.app.ui import callbacks as ui_cbs
from hubplatform.telegram.app.ui.finalizers import StripAndNavigationFinalizer

from . import callbacks as cbs


registry = UIRegistry()


BUTTON_BUILDERS: dict[type[Node], CallableWrapper[KeyboardBlockSpec]] = {}

_N = TypeVar('_N', bound=Node, default=Any, contravariant=True)
_C = TypeVar('_C', bound=MenuContext, default=Any, contravariant=True)
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


class ListNodeMenuContext(NodeMenuContext):
    selected_indexes: set[int]
    editing: bool = False


@registry.add_menu_builder(
    menu_id='hubplatform.pyconfigtree.properties', context_type=NodeMenuContext
)
async def properties_menu_builder(
    ctx: NodeMenuContext, properties: Properties, tr: Translator, app_context: Mapping[str, Any]
) -> MenuBuildingSpec:
    node = properties.get_node(path=ctx.node_path)
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


@registry.add_menu_builder(
    menu_id='hubplatform.pyconfigtree.list_param', context_type=ListNodeMenuContext
)
class ListParamMenuBuilder:
    async def __call__(
        self,
        ctx: ListNodeMenuContext,
        properties: Properties,
        tr: Translator,
        app_context: Mapping[str, Any],
    ) -> MenuBuildingSpec:
        node = properties.get_parameter(ctx.node_path)
        menu_spec = MenuSpec()
        if not isinstance(node, ListParameter):
            raise TypeError('Cannot build list param menu for not a ListParameter.')
        for index, val in enumerate(node.value):
            if ctx.editing:
                menu_spec.main_keyboard.append(
                    KeyboardBlockSpec(
                        block_id=f'hubplatform.pyconfigtree.list_param.item.{index}',
                        builder=partial(
                            self.build_list_item_button, ctx, val, index, ctx.selected_indexes
                        ),
                    )
                )
            else:
                menu_spec.main_keyboard.append(
                    KeyboardBlockSpec.copy_text_button(
                        block_id=f'hubplatform.pyconfigtree.list_param.item.{index}',
                        text=str(val),
                        copy_text=str(val),
                    )
                )

        menu_spec.footer_keyboard.append(
            KeyboardBlockSpec(
                block_id='hubplatform.pyconfigtree.list_param.change_mode',
                builder=partial(self.build_change_mode_button, ctx),
            )
        )

        if ctx.selected_indexes:
            menu_spec.footer_keyboard.append(
                KeyboardBlockSpec(
                    block_id='hubplatform.pyconfigtree.list_param.control',
                    builder=partial(
                        self.build_control_panel,
                        ctx,
                        ctx.selected_indexes,
                    ),
                )
            )

        menu_spec.body_text = 'List param'
        return MenuBuildingSpec(menu=menu_spec, finalizer=StripAndNavigationFinalizer())

    async def build_change_mode_button(self, ctx: ListNodeMenuContext) -> Keyboard:
        return [
            [
                Button(
                    button_id='hubplatform.pyconfigtree.list_param.change_mode',
                    text='✏️' if not ctx.editing else '⬅️🚪',
                    callback_data=ui_cbs.OpenMenu(
                        snapshot=ctx.model_copy(update={'editing': not ctx.editing}).snapshot()
                    ),
                )
            ]
        ]

    async def build_control_panel(
        self, ctx: ListNodeMenuContext, selected_indexes: set[int]
    ) -> Keyboard:
        buttons = []
        cancel_ctx = ctx.model_copy(update={'selected_indexes': set()})
        buttons.append(
            Button(
                button_id='hubplatform.pyconfigtree.list_param.control.move_up',
                text='⬆️',
                callback_data=ui_cbs.Dummy(),
            )
        )
        buttons.append(
            Button(
                button_id='hubplatform.pyconfigtree.list_param.control.move_down',
                text='⬇️',
                callback_data=ui_cbs.Dummy(),
            )
        )
        buttons.append(
            Button(
                button_id='hubplatform.pyconfigtree.list_param.control.remove',
                text='🗑️',
                callback_data=ui_cbs.Dummy(),
            )
        )
        buttons.append(
            Button(
                button_id='hubplatform.pyconfigtree.list_param.control.cancel_selection',
                text='❌',
                callback_data=ui_cbs.OpenMenu(snapshot=cancel_ctx.snapshot()),
            )
        )
        return [buttons]

    async def build_list_item_button(
        self, ctx: ListNodeMenuContext, item: Any, index: int, selected_indexes: set[int]
    ) -> Keyboard:
        new_ctx = ctx.model_copy(deep=False)
        new_indexes = new_ctx.selected_indexes.copy()
        if index in new_indexes:
            new_indexes.remove(index)
        else:
            new_indexes.add(index)
        new_ctx.selected_indexes = new_indexes

        button = Button(
            button_id=f'hubplatform.pyconfigtree.list_param.item.{index}',
            text=str(item),
            style='primary' if index in selected_indexes else None,
            callback_data=ui_cbs.OpenMenu(snapshot=new_ctx.snapshot()),
        )
        return [[button]]


@register_node_button_builder(Properties)
async def properties_button_builder(
    node: Properties, i18n: Translator, menu_ctx: MenuContext
) -> KeyboardBlockSpec:
    ctx = NodeMenuContext(
        menu_id='hubplatform.pyconfigtree:node',
        node_path=list(node.path),
        ui_history=menu_ctx.as_ui_history(),
    )

    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree:properties',
        text=i18n.translate(node.name),
        callback_data=ui_cbs.OpenMenu(snapshot=ctx.snapshot()),
    )


@register_node_button_builder(BoolParameter)
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
        callback_data=cbs.NextValue(node_path=list(node.path), open_next=menu_ctx.snapshot()),
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
    menu_ctx: MenuContext,
) -> KeyboardBlockSpec:
    for t, block_id in _ids.items():
        if isinstance(node, t):
            break
    else:
        raise ValueError('Unsupported node type.')

    return KeyboardBlockSpec.callback_button(
        block_id=f'hubplatform.pyconfigtree.{block_id}',
        text=i18n.translate(node.name),
        callback_data=cbs.ManualValueInput(
            node_path=list(node.path), open_next=menu_ctx.snapshot()
        ),
    )


@register_node_button_builder(ListParameter)
async def list_parameter_button_builder(
    node: ListParameter[Any],
    i18n: Translator,
    menu_ctx: MenuContext,
) -> KeyboardBlockSpec:
    ctx = ListNodeMenuContext(
        menu_id='hubplatform.pyconfigtree.list_param',
        node_path=list(node.path),
        selected_indexes=set(),
        ui_history=menu_ctx.as_ui_history(),
    )

    return KeyboardBlockSpec.callback_button(
        block_id='hubplatform.pyconfigtree.list_param',
        text=i18n.translate(node.name),
        callback_data=ui_cbs.OpenMenu(snapshot=ctx.snapshot()),
    )
