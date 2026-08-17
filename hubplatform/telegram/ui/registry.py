from __future__ import annotations

import inspect
from typing import Any, TypeVar, Callable, Protocol, ParamSpec, Concatenate
from dataclasses import field, dataclass
from collections import defaultdict
from collections.abc import Mapping, Sequence, Awaitable

from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.logging.loggers import telegram as _logger

from .types import MenuSpec, MenuContext


logger = _logger.ui

_P = ParamSpec('_P', default=...)
MenuBuilder = Callable[Concatenate[MenuContext, _P], Awaitable[MenuSpec]]
MenuModification = Callable[Concatenate[MenuContext, 'MenuBuildingState', _P], Awaitable[MenuSpec]]
MenuModificationFilter = Callable[
    Concatenate[MenuContext, 'MenuBuildingState', _P], Awaitable[bool]
]


class MenuBuilderProto(Protocol[_P]):
    async def __call__(self, _c: MenuContext, /, *_a: _P.args, **_k: _P.kwargs) -> MenuSpec: ...


class MenuModificationProto(Protocol[_P]):
    async def __call__(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec: ...


class MenuModificationWithFilterProto(MenuModificationProto[_P], Protocol[_P]):
    async def filter(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> bool: ...


_MenuBuilderType = MenuBuilder | type[MenuBuilderProto]
_MenuModificationType = (
    MenuModification | type[MenuModificationProto] | type[MenuModificationWithFilterProto]
)


@dataclass
class MenuBuildingState:
    menu: MenuSpec
    pending_modifications: list[MenuModificationMeta]


@dataclass(frozen=True)
class MenuBuilderMeta:
    _callable_wrapper: CallableWrapper[MenuSpec] = field(init=False)
    _is_class: bool = field(init=False)

    id: str
    builder_obj: _MenuBuilderType

    def __post_init__(self) -> None:
        object.__setattr__(self, '_is_class', isinstance(self.builder_obj, type))
        object.__setattr__(
            self,
            '_callable_wrapper',
            CallableWrapper(self.builder_obj.__call__ if self._is_class else self.builder_obj),
        )

    async def build(
        self,
        menu_context: MenuContext,
        args: Sequence[Any],
        data: Mapping[str, Any],
        modifications: list[MenuModificationMeta],
    ) -> MenuSpec:
        if self._is_class:
            total_args = [self.builder_obj(), menu_context, *args]
        else:
            total_args = [menu_context, *args]

        result = await self._callable_wrapper(args=total_args, data=data)
        if not isinstance(result, MenuSpec):
            raise Exception('not a menu spec')  # todo

        mods = modifications.copy()
        while mods:
            mod = mods.pop()
            try:
                state = MenuBuildingState(menu=result, pending_modifications=mods.copy())
                mod_result = await mod.build(menu_context, state, args=args, data=data)
                if isinstance(mod_result, MenuSpec):
                    result = mod_result
                elif isinstance(mod_result, MenuBuildingState):
                    result = state.menu
                    mods = state.pending_modifications
                else:
                    logger.error(
                        'An error occurred while running modification %s for menu %s: '
                        'modification return %s, but expected `MenuSpec` or `MenuBuildingState. '
                        'Skipping modification.',
                        mod.id,
                        menu_context.menu_id,
                        type(mod_result).__name__,
                    )
            except Exception as e:
                logger.exception(
                    'An error occurred while running modification %s for menu %s. '
                    'Skipping modification.',
                    mod.id,
                    menu_context.menu_id,
                    exc_info=e,
                )

        return result


@dataclass(frozen=True)
class MenuModificationMeta:
    _is_class: bool = field(init=False)
    _explicit_filter_wrapper: CallableWrapper[bool] | None = field(init=False, default=None)
    _filter_from_mod_wrapper: CallableWrapper[bool] | None = field(init=False, default=None)
    _modification_wrapper: CallableWrapper[MenuBuildingState] = field(init=False)

    id: str
    menu_id: str
    modification: _MenuModificationType
    filter: MenuModificationFilter[Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, '_is_class', isinstance(self.modification, type))
        object.__setattr__(
            self,
            '_callable_wrapper',
            CallableWrapper(self.modification.__call__ if self._is_class else self.modification),
        )
        if self.filter is not None:
            object.__setattr__(self, '_explicit_filter_wrapper', CallableWrapper(self.filter))

        if (
            self._is_class
            and hasattr(self.modification, 'filter')
            and inspect.isfunction(self.modification.filter)
        ):
            object.__setattr__(
                self, '_filter_from_mod_wrapper', CallableWrapper(self.modification.filter)
            )

    async def run_filter(self, args: Sequence[Any], data: Mapping[str, Any]) -> bool:
        if self._explicit_filter_wrapper is not None:
            result = bool(await self._explicit_filter_wrapper(args=args, data=data))
            if not result:
                return False

        if self._filter_from_mod_wrapper is not None:
            result = bool(await self._filter_from_mod_wrapper(args=args, data=data))
            if not result:
                return False

        return True

    async def build(
        self,
        menu_context: MenuContext,
        menu_state: MenuBuildingState,
        args: Sequence[Any],
        data: Mapping[str, Any],
    ) -> MenuBuildingState:
        args = [menu_context, menu_state, *args]

        if not (await self.run_filter(args=args, data=data)):
            return menu_state

        result = await self._modification_wrapper(args=args, data=data)
        if not isinstance(result, MenuBuildingState):
            print('not a building state')  # todo: loggin
            result = menu_state

        return result


_MB = TypeVar('_MB', bound=_MenuBuilderType)
_MM = TypeVar('_MM', bound=_MenuModificationType)


class UIRegistry:
    def __init__(self, *, context: Mapping[str, Any] | None = None) -> None:
        self._context = context if context is not None else {}
        self._menus: dict[str, MenuBuilderMeta] = {}
        self._menu_modifications: dict[str, dict[str, Any]] = defaultdict(dict)

    def add_menu_builder(self, menu_id: str) -> Callable[[_MB], _MB]:
        if not isinstance(menu_id, str):
            raise TypeError('menu_id must be a string.')
        if not menu_id:
            raise ValueError('menu_id cannot be empty.')
        if menu_id == '*':
            raise ValueError('Invalid menu_id.')
        if menu_id in self._menus:
            raise RuntimeError(f'Menu {menu_id!r} already registered.')

        def inner(builder: _MB) -> _MB:
            self._menus[menu_id] = MenuBuilderMeta(id=menu_id, builder_obj=builder)
            return builder

        return inner

    def add_menu_modification(
        self, menu_id: str, modification_id: str, filter: MenuModificationFilter | None = None
    ) -> Callable[[_MM], _MM]:
        if not isinstance(menu_id, str):
            raise TypeError('menu_id must be a string.')
        if not menu_id:
            raise ValueError('menu_id cannot be empty.')
