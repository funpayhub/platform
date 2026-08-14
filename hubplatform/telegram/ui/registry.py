from collections.abc import Callable, Mapping
from typing import overload, Any

from .types import Menu, MenuContext, ButtonSpec, ButtonContext
from .builders import MenuBuilder, ButtonBuilder, MenuModification, ButtonModification


_REGISTRABLE = type[MenuBuilder | ButtonBuilder | MenuModification | ButtonModification]

class UIRegistry:
    def __init__(self, *, context: Mapping[str, Any] | None = None) -> None:
        self._menus: dict[str, type[MenuBuilder]] = {}
        self._buttons: dict[str, type[ButtonBuilder]] = {}
        self._menu_mods: dict[str, type[MenuModification]] = {}
        self._button_mods: dict[str, type[ButtonModification]] = {}
        self._context = context if context is not None else {}

    @overload
    def register[R](self, cls: None = None, *, overwrite: bool = False) -> Callable[[R], R]: pass

    @overload
    def register[R: _REGISTRABLE](self, cls: R, *, overwrite: bool = False) -> R: pass

    def register[R: _REGISTRABLE](self, cls: R | None = None, *, overwrite: bool = False) -> R | Callable[[R], R]:
        def _register(cls: R) -> R:
            if not isinstance(cls, type):
                raise TypeError('must be a subclass of _REGISTRABLE') # todo

            for type_, dict_ in (
                (MenuBuilder, self._menus),
                (ButtonBuilder, self._buttons),
                (MenuModification, self._menu_mods),
                (ButtonModification, self._button_mods),
            ):
                if issubclass(cls, type_):
                    if cls.id in dict_ and not overwrite:
                        raise ValueError(
                            f'{type_.__name__!r} with id {cls.id!r} is already registered.'
                        )
                    dict_[cls.id] = cls  # type: ignore[assignment]
                    return cls
            raise TypeError('must be a subclass of _REGISTRABLE') # todo

        if cls is None:
            return _register
        return _register(cls)

    def include_from_registry(self, registry: UIRegistry, overwrite: bool = False) -> None:
        ...

    def include_from_registries(self, *registries: UIRegistry, overwrite: bool = False) -> None:
        ...

    async def build_menu(self, ctx: MenuContext) -> Menu:
        if ctx.menu_id not in self._menus:
            ...

    async def build_button(self, ctx: ButtonContext) -> ButtonSpec:
        ...