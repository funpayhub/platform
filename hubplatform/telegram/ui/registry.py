from __future__ import annotations

from typing import Any, overload
from functools import partial
from collections import defaultdict
from collections.abc import Mapping, Callable

from .types import Menu, ButtonSpec, MenuContext, ButtonContext
from .builders import MenuBuilder, ButtonBuilder, MenuModification, ButtonModification


_REGISTRABLE = type[MenuBuilder | ButtonBuilder | MenuModification | ButtonModification]


class UIRegistry:
    def __init__(self, *, context: Mapping[str, Any] | None = None) -> None:
        self._menus: dict[str, type[MenuBuilder]] = {}
        self._buttons: dict[str, type[ButtonBuilder]] = {}
        self._menu_mods: dict[str, dict[str, list[type[MenuModification]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._button_mods: dict[str, dict[str, list[type[ButtonModification]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._context = context if context is not None else {}

    @overload
    def register[R](self, cls: None = None, *, overwrite: bool = False) -> Callable[[R], R]:
        pass

    @overload
    def register[R: _REGISTRABLE](self, cls: R, *, overwrite: bool = False) -> R:
        pass

    def register[R: _REGISTRABLE](
        self, cls: R | None = None, *, for_id: str | None = None, overwrite: bool = False
    ) -> R | Callable[[R], R]:
        if cls is None:
            return partial(self._register, for_id=for_id, overwrite=overwrite)
        return self._register(cls, for_id=for_id, overwrite=overwrite)

    def _register[R: _REGISTRABLE](
        self, cls: R, *, for_id: str | None = None, overwrite: bool = False
    ) -> R:
        if not isinstance(cls, type):
            raise TypeError('must be a subclass of _REGISTRABLE')  # todo

        for type_, dict_ in (
            (MenuBuilder, self._menus),
            (ButtonBuilder, self._buttons),
        ):
            if issubclass(cls, type_):
                if cls.id in dict_ and not overwrite:
                    raise RuntimeError(
                        f'{type_.__name__!r} with id {cls.id!r} is already registered.'
                    )
                dict_[cls.id] = cls  # type: ignore[assignment]
                return cls

        for type_, dict_ in (
            (MenuModification, self._menu_mods),
            (ButtonBuilder, self._button_mods),
        ):
            if issubclass(cls, type_):
                if for_id is None:
                    raise ValueError("For modifications 'for_id' must be specified.")
                if cls.id in dict_[for_id] and not overwrite:
                    raise RuntimeError(
                        f'{type_.__name__!r} with id {cls.id!r} for {for_id!r} is already registered.'
                    )
                dict_[for_id][cls.id] = cls  # type: ignore[assignment]
                return cls

        raise TypeError('must be a subclass of _REGISTRABLE')  # todo

    def include_from_registry(self, registry: UIRegistry, overwrite: bool = False) -> None: ...

    def include_from_registries(
        self, *registries: UIRegistry, overwrite: bool = False
    ) -> None: ...

    async def build_menu(self, ctx: MenuContext) -> Menu:
        if ctx.menu_id not in self._menus:
            ...

    async def build_button(self, ctx: ButtonContext) -> ButtonSpec: ...
