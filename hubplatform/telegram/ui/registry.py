from __future__ import annotations


__all__ = [
    'UIRegistry',
    'MenuBuilderType',
    'MenuModificationType',
    'MenuFinalizerType',
    'MenuBuildingSpec',
    'MenuBuildingState',
    'MenuModificationMeta',
    'global_ui_registry',
]

import inspect
from typing import Any, Union, TypeVar, Protocol, ParamSpec, runtime_checkable
from dataclasses import field as dataclass_field
from collections import defaultdict
from collections.abc import Mapping, Callable, Sequence

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.logging.loggers import telegram as _logger
from hubplatform.telegram.callback_data.hash.service import HashService, global_hash_service

from . import MenuRuntimeContext, MenuContextSnapshot
from .types import MenuSpec, MenuContext, MenuRenderResult
from .exceptions import MenuBuildingError, MenuFinalizingError, MenuModificationError


logger = _logger.ui

_P = ParamSpec('_P', default=...)
_C = TypeVar('_C', bound=MenuContext, default=Any, contravariant=True)


@runtime_checkable
class MenuBuilderProto(Protocol[_P, _C]):
    async def __call__(
        self, _c: _C, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec | MenuBuildingSpec: ...


@runtime_checkable
class MenuModificationProto(Protocol[_P, _C]):
    async def __call__(
        self, _c: _C, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> MenuSpec | MenuBuildingState: ...


@runtime_checkable
class MenuModificationFilterProto(Protocol[_P, _C]):
    async def __call__(
        self, _c: _C, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> bool: ...


@runtime_checkable
class MenuModificationWithFilterProto(MenuModificationProto[_P, _C], Protocol[_P, _C]):
    async def filter(
        self, _C: MenuContext, _s: MenuBuildingState, /, *_a: _P.args, **_k: _P.kwargs
    ) -> bool: ...


@runtime_checkable
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
    modifications: list[MenuModificationMeta] = dataclass_field(default_factory=list)
    finalizer: MenuFinalizerType | None = None


@pydantic_dataclass(config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True))
class MenuBuildingState:
    menu: MenuSpec
    pending_modifications: list[MenuModificationMeta] = dataclass_field(default_factory=list)
    finalizer: MenuFinalizerType | None = None


@pydantic_dataclass(
    frozen=True, config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)
)
class _MenuBuilderMeta:
    menu_id: str
    builder: MenuBuilderType
    context_type: type[MenuContext]

    _builder_wrapped: CallableWrapper[MenuSpec] = dataclass_field(init=False)
    _is_class: bool = dataclass_field(init=False)

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
            args = (
                [
                    self.builder(),  # type: ignore[call-arg]  # init must have no args
                    menu_context,
                ]
                if self._is_class
                else [menu_context]
            )
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


@pydantic_dataclass(
    frozen=True, config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)
)
class MenuModificationMeta:
    modification_id: str
    menu_id: str
    modification: MenuModificationType
    filter: MenuModificationFilterProto | None = None

    _is_class: bool = dataclass_field(init=False)
    _explicit_filter_wrapped: CallableWrapper[bool] | None = dataclass_field(
        init=False, default=None
    )
    _filter_from_mod_wrapped: CallableWrapper[bool] | None = dataclass_field(
        init=False, default=None
    )
    _modification_wrapped: CallableWrapper[MenuBuildingState] = dataclass_field(init=False)

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
                instance_args = [
                    self.modification(),  # type: ignore[call-arg]  # init must have no args
                    menu_context,
                    menu_state,
                ]

            if not (
                await self._run_filter(
                    args=args, instance_args=instance_args, di_context=di_context
                )
            ):
                return menu_state

            result = await self._modification_wrapped(args=instance_args, data=di_context)
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
            wrapped: CallableWrapper[MenuSpec] = CallableWrapper(state.finalizer)
            result = await wrapped(args=[menu_context, state], data=di_context)
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
        result = state.menu

    return result


_MB = TypeVar('_MB', bound=MenuBuilderType)
_MM = TypeVar('_MM', bound=MenuModificationType)


class UIRegistry:
    def __init__(
        self, *, context: Mapping[str, Any] | None = None, hash_service: HashService | None = None
    ) -> None:
        self._context = context if context is not None else {}
        self._menus: dict[str, _MenuBuilderMeta] = {}
        self._menu_modifications: dict[str, dict[str, MenuModificationMeta]] = defaultdict(dict)
        self._global_modifications: dict[str, MenuModificationMeta] = {}
        self._hash_service = hash_service

    def get_menu_context_type(self, menu_id: str) -> type[MenuContext]:
        if menu_id not in self._menus:
            raise KeyError(f'Menu {menu_id!r} not registered.')

        return self._menus[menu_id].context_type

    def context_from_snapshot(
        self, snapshot: MenuContextSnapshot, *, runtime: MenuRuntimeContext | None = None
    ) -> MenuContext:
        ctx = self.get_menu_context_type(snapshot.menu_id)
        return ctx.from_snapshot(snapshot, runtime=runtime)

    def context_from_history(
        self, ui_history: list[MenuContextSnapshot], *, runtime: MenuRuntimeContext | None = None
    ) -> MenuContext:
        if not ui_history:
            raise ValueError('ui_history cannot be empty.')
        snapshot, history = ui_history[-1], ui_history[:-1]
        ctx = self.get_menu_context_type(snapshot.menu_id)
        return ctx.from_snapshot(snapshot, ui_history=history, runtime=runtime)

    def add_menu_builder(
        self, menu_id: str, context_type: type[MenuContext] = MenuContext
    ) -> Callable[[_MB], _MB]:
        if not isinstance(menu_id, str):
            raise TypeError('menu_id must be a string.')
        if not menu_id:
            raise ValueError('menu_id cannot be empty.')
        if menu_id == '*':
            raise ValueError('Invalid menu_id.')
        if menu_id in self._menus:
            raise RuntimeError(f'Menu {menu_id!r} already registered.')

        def inner(builder: _MB) -> _MB:
            self._menus[menu_id] = _MenuBuilderMeta(
                menu_id=menu_id, builder=builder, context_type=context_type
            )
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

        if menu_id == '*':
            storage = self._global_modifications
        else:
            storage = self._menu_modifications[menu_id]

        if modification_id in storage:
            raise RuntimeError(
                f'Menu modification {modification_id!r} for menu {menu_id!r} already registered.'
            )

        def inner(modification: _MM) -> _MM:

            storage[modification_id] = MenuModificationMeta(
                modification_id=modification_id,
                menu_id=menu_id,
                filter=filter,
                modification=modification,
            )
            return modification

        return inner

    def merge_from(self, *registries: UIRegistry, skip_existing: bool = False) -> None:
        if not registries:
            return

        if len(registries) == 1:
            self._merge_single(registries[0], skip_existing=skip_existing)
            return

        temp_registry = UIRegistry()
        for registry in registries:
            temp_registry.merge_from(registry, skip_existing=skip_existing)

        self._merge_single(temp_registry, skip_existing=skip_existing)

    def _merge_single(self, ui_registry: 'UIRegistry', *, skip_existing: bool = False) -> None:
        if not isinstance(ui_registry, UIRegistry):
            raise TypeError('ui_registry must be an instance of `UIRegistry`.')

        if ui_registry is self:
            return

        if not skip_existing:
            if conflicting_menus := self._menus.keys() & ui_registry._menus.keys():
                raise RuntimeError(f'Menus {", ".join(conflicting_menus)} already registered.')

            conflicting_global_modifications = (
                self._global_modifications.keys() & ui_registry._global_modifications.keys()
            )
            if conflicting_global_modifications:
                raise RuntimeError(
                    f'Global menu modifications {", ".join(conflicting_global_modifications)} '
                    f'already registered.'
                )

            for menu_id, modifications in ui_registry._menu_modifications.items():
                current = self._menu_modifications.get(menu_id)
                if not current:
                    continue

                conflicts = current.keys() & modifications.keys()
                if conflicts:
                    raise RuntimeError(
                        f'Menu modifications {", ".join(conflicts)} '
                        f'for menu {menu_id!r} already registered.'
                    )

        if skip_existing:
            for menu_id, menu in ui_registry._menus.items():
                self._menus.setdefault(menu_id, menu)

            for modification_id, modification in ui_registry._global_modifications.items():
                self._global_modifications.setdefault(modification_id, modification)

            for menu_id, modifications in ui_registry._menu_modifications.items():
                current = self._menu_modifications[menu_id]

                for modification_id, modification in modifications.items():
                    current.setdefault(modification_id, modification)

        else:
            self._menus |= ui_registry._menus
            self._global_modifications |= ui_registry._global_modifications

            for menu_id, modifications in ui_registry._menu_modifications.items():
                self._menu_modifications[menu_id] |= modifications

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
                *self._menu_modifications[menu_context.menu_id].values(),
            ],
            di_context=self._context,
        )

        result = await menu_spec.render(
            di_context=self._context,
            hash_service=hash_service if hash_service is not None else self._hash_service,
        )

        if result.building_errors:
            logger.warning(
                'Menu %s build completed with %d errors.',
                menu_context.menu_id,
                len(result.building_errors),
            )

        if result.render_errors:
            logger.warning(
                'Menu %s render completed with %d errors.',
                menu_context.menu_id,
                len(result.render_errors),
            )

        for index, building_error in enumerate(result.building_errors):
            logger.warning(
                '%d. An error occurred while building keyboard block %s.',
                index + 1,
                building_error.block_id,
                exc_info=building_error,
            )

        for index, render_error in enumerate(result.render_errors):
            logger.warning(
                '%d. An error occurred while rendering button %s.',
                index + 1,
                render_error.button_id,
                exc_info=render_error,
            )

        return result


_UI_REGISTRY: UIRegistry | None = None


def global_ui_registry() -> UIRegistry:
    global _UI_REGISTRY
    if _UI_REGISTRY is None:
        _UI_REGISTRY = UIRegistry(hash_service=global_hash_service())
    return _UI_REGISTRY
