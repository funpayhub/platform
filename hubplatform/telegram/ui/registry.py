from __future__ import annotations

import inspect
from typing import Any, Union, Protocol, ParamSpec, TypeVar
from collections import defaultdict
from dataclasses import field, dataclass
from collections.abc import Mapping, Sequence, Callable

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.logging.loggers import telegram as _logger
from . import MenuRenderResult

from .types import MenuSpec, MenuContext
from .exceptions import MenuBuildingError, MenuFinalizingError, MenuModificationError
from ..callback_data.hash import HashService

logger = _logger.ui

_P = ParamSpec('_P', default=...)


class MenuBuilderProto(Protocol[_P]):
    async def __call__(
        self, _c: MenuContext, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec | MenuBuildingSpec: ...


class MenuModificationProto(Protocol[_P]):
    async def __call__(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec | MenuBuildingState: ...


class MenuModificationFilterProto(Protocol[_P]):
    async def __call__(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> bool: ...


class MenuModificationWithFilterProto(MenuModificationProto[_P], Protocol[_P]):
    async def filter(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> bool: ...


class MenuFinalizerProto(Protocol[_P]):
    async def __call__(
        self, _c: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec: ...


MenuBuilderType = MenuBuilderProto | type[MenuBuilderProto]
MenuModificationType = Union[
    MenuModificationProto,
    MenuModificationWithFilterProto,
    type[MenuModificationProto],
    type[MenuModificationWithFilterProto],
]
MenuFinalizerType = MenuFinalizerProto


@pydantic_dataclass(config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class MenuBuildingSpec:
    menu: MenuSpec
    modifications: list[MenuModificationMeta] = field(default_factory=list)
    finalizer: MenuFinalizerType | None = None


@pydantic_dataclass(config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class MenuBuildingState:
    menu: MenuSpec
    pending_modifications: list[MenuModificationMeta] = field(default_factory=list)
    finalizer: MenuFinalizerType | None = None


@pydantic_dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class _MenuBuilderMeta:
    _builder_wrapped: CallableWrapper[MenuSpec] = field(init=False)
    _is_class: bool = field(init=False)

    menu_id: str
    builder: MenuBuilderType

    def __post_init__(self) -> None:
        object.__setattr__(self, '_is_class', isinstance(self.builder, type))
        object.__setattr__(
            self,
            '_builder_wrapped',
            CallableWrapper(self.builder.__call__ if self._is_class else self.builder),
        )

    async def build(
        self,
        menu_context: MenuContext,
        di_context: Mapping[str, Any],
    ) -> MenuBuildingSpec:
        try:
            args = [self.builder(), menu_context] if self._is_class else [menu_context]
            result = await self._builder_wrapped(args=args, data=di_context)
        except Exception as e:
            raise MenuBuildingError(menu_id=self.menu_id) from e

        if isinstance(result, MenuSpec):
            return MenuBuildingSpec(menu=result, modifications=[], finalizer=None)
        if isinstance(result, MenuBuildingSpec):
            return result
        raise MenuBuildingError(
            menu_id=self.menu_id,
            message=f'Menu builder {self.menu_id!r} returned unexpected type. '
            f'Expected: `MenuSpec` or `MenuBuildingSpec`, '
            f'got: {result.__class__.__name__!r}.',
        )


@pydantic_dataclass(frozen=True, config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class MenuModificationMeta:
    _is_class: bool = field(init=False)
    _explicit_filter_wrapped: CallableWrapper[bool] | None = field(init=False, default=None)
    _filter_from_mod_wrapped: CallableWrapper[bool] | None = field(init=False, default=None)
    _modification_wrapped: CallableWrapper[MenuBuildingState] = field(init=False)

    modification_id: str
    menu_id: str
    modification: MenuModificationProto | MenuModificationWithFilterProto
    filter: MenuModificationFilterProto | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, '_is_class', isinstance(self.modification, type))
        object.__setattr__(
            self,
            '_modification_wrapped',
            CallableWrapper(self.modification.__call__ if self._is_class else self.modification),
        )
        if self.filter is not None:
            object.__setattr__(self, '_explicit_filter_wrapped', CallableWrapper(self.filter))

        if (
            self._is_class
            and hasattr(self.modification, 'filter')
            and inspect.isfunction(self.modification.filter)
        ):
            object.__setattr__(
                self, '_filter_from_mod_wrapped', CallableWrapper(self.modification.filter)
            )

    async def _run_filter(
        self, args: Sequence[Any], instance_args: Sequence[Any], di_context: Mapping[str, Any]
    ) -> bool:
        if self._explicit_filter_wrapped is not None:
            result = bool(await self._explicit_filter_wrapped(args=args, data=di_context))
            if not result:
                return False

        if self._filter_from_mod_wrapped is not None:
            result = bool(await self._filter_from_mod_wrapped(args=instance_args, data=di_context))
            if not result:
                return False

        return True

    async def build(
        self,
        menu_context: MenuContext,
        menu_state: MenuBuildingState,
        di_context: Mapping[str, Any],
    ) -> MenuBuildingState:
        try:
            args = instance_args = [menu_context, menu_state]
            if self._is_class:
                instance_args = [self.modification(), menu_context, menu_state]

            if not (
                await self._run_filter(
                    args=args, instance_args=instance_args, di_context=di_context
                )
            ):
                return menu_state

            result = await self._modification_wrapped(args=args, data=di_context)
        except Exception as e:
            raise MenuModificationError(
                menu_id=self.menu_id, modification_id=self.modification_id
            ) from e

        if isinstance(result, MenuBuildingState):
            return result
        if isinstance(result, MenuSpec):
            return MenuBuildingState(
                menu=result,
                pending_modifications=menu_state.pending_modifications,
                finalizer=menu_state.finalizer,
            )
        raise MenuModificationError(
            menu_id=self.menu_id,
            modification_id=self.modification_id,
            message=f'Menu modification {self.modification_id!r} for menu {self.menu_id} '
            f'returned unexpected type. '
            f'Expected: `MenuSpec` or `MenuBuildingState`, '
            f'got: {result.__class__.__name__!r}.',
        )


async def build_menu(
    menu_builder: _MenuBuilderMeta,
    menu_context: MenuContext,
    modifications: list[MenuModificationMeta],
    di_context: Mapping[str, Any],
) -> MenuSpec:
    menu = await menu_builder.build(menu_context=menu_context, di_context=di_context)
    state = MenuBuildingState(
        menu=menu.menu,
        pending_modifications=[*menu.modifications, *modifications],
        finalizer=menu.finalizer,
    )

    while True:
        if not state.pending_modifications:
            break
        mod = state.pending_modifications.pop(0)
        state = await mod.build(menu_context=menu_context, menu_state=state, di_context=di_context)

    if state.finalizer is not None:
        try:
            wrapped = CallableWrapper(state.finalizer)
            result = await wrapped(args=[state, menu_context], data=di_context)
        except Exception as e:
            raise MenuFinalizingError(menu_id=menu_builder.menu_id) from e

        if not isinstance(result, MenuSpec):
            raise MenuFinalizingError(
                menu_id=menu_builder.menu_id,
                message=f'Menu finalizer for menu {menu_builder.menu_id!r}'
                f'returned an unexpected type. '
                f'Expected: `MenuSpec`, got: {result.__class__.__name__!r}.',
            )
    else:
        result = state

    return result


_MB = TypeVar('_MB', bound=MenuBuilderType)
_MM = TypeVar('_MM', bound=MenuModificationType)


class UIRegistry:
    def __init__(self, *, context: Mapping[str, Any] | None = None, hash_serivce: HashService | None = None) -> None:
        self._context = context if context is not None else {}
        self._menus: dict[str, _MenuBuilderMeta] = {}
        self._menu_modifications: dict[str, dict[str, MenuModificationMeta]] = defaultdict(dict)
        self._global_modifications: dict[str, MenuModificationMeta] = {}
        self._hash_service = hash_serivce

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
            self._menus[menu_id] = _MenuBuilderMeta(menu_id=menu_id, builder=builder)
            return builder

        return inner

    def add_menu_modification(
        self, menu_id: str, modification_id: str, filter: MenuModificationFilterProto | None = None
    ) -> Callable[[_MM], _MM]:
        if not isinstance(menu_id, str):
            raise TypeError('menu_id must be a string.')
        if not menu_id:
            raise ValueError('menu_id cannot be empty.')
        if not isinstance(modification_id, str):
            raise TypeError('modification_id must be a string.')
        if not modification_id:
            raise ValueError('modification_id cannot be empty.')
        if menu_id in self._menu_modifications and modification_id in self._menu_modifications[menu_id]:
            raise RuntimeError(
                f'Menu modification {modification_id!r} for menu {menu_id!r} already registered.'
            )

        def inner(modification: _MM) -> _MM:
            self._menu_modifications[menu_id][modification_id] = MenuModificationMeta(
                modification_id=modification_id,
                menu_id=menu_id,
                filter=filter,
                modification=modification
            )
            return modification

        return inner

    async def build_menu(
        self,
        menu_context: MenuContext,
        hash_service: HashService | None = None,
    ) -> MenuRenderResult:
        if not isinstance(menu_context, MenuContext):
            raise TypeError('menu_context must be an instance of `MenuContext`.')
        if menu_context.menu_id not in self._menus:
            raise KeyError(f'Menu {menu_context.menu_id!r} not registered.')

        menu_spec = await build_menu(
            menu_builder=self._menus[menu_context.menu_id],
            menu_context=menu_context,
            modifications=[
                *self._global_modifications.values(),
                *self._menu_modifications[menu_context.menu_id].values()
            ],
            di_context=self._context
        )

        return await menu_spec.render(
            di_context=self._context,
            hash_service=hash_service if hash_service is not None else self._hash_service
        )
