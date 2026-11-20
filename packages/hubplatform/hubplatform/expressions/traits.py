from __future__ import annotations


__all__ = [
    'Trait',
    'TraitsContainer',
    'TraitsView',
]

from typing import Any, ClassVar, overload
from collections.abc import Iterable, Iterator

from pydantic import BaseModel

from .exceptions import UndeclaredTraitError


class Trait(BaseModel):
    """A small piece of data that a text is evaluated with: an order, a message, a user, ...

    Every subclass has a name and a description, which are shown in the documentation UI::

        class OrderTrait(Trait, name='Заказ', description='...'):
            order_id: str

    A trait inherits from another trait only for a real "is a" relationship: a FunPay order
    is an order, so ``FunPayOrderTrait(OrderTrait)``. A trait never inherits from another one
    just to share fields; data about another entity (for example, the user who made the order)
    is a separate trait.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    def __init_subclass__(
        cls, name: str | None = None, description: str | None = None, **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        if name is None:
            raise ValueError(f'Trait name is not specified for {cls.__qualname__}.')
        if description is None:
            raise ValueError(f'Trait description is not specified for {cls.__qualname__}.')

        cls.name = name
        cls.description = description


class TraitsContainer:
    """The traits a text is evaluated with.

    ``container[T]`` returns the first trait that is an instance of ``T``, including instances of
    its subclasses. A container can hold several traits of the same type;
    ``get_all_traits(T)`` returns all of them.
    """

    __slots__ = ('_traits', '_shape')

    def __init__(self, *traits: Trait) -> None:
        for trait in traits:
            if not isinstance(trait, Trait):
                raise TypeError(f'A trait must be an instance of `Trait`, not {trait!r}.')
        self._traits = traits
        self._shape = frozenset(type(i) for i in traits)

    @property
    def traits(self) -> tuple[Trait, ...]:
        """Every trait in the container, in the order they were passed."""
        return self._traits

    @property
    def shape(self) -> frozenset[type[Trait]]:
        """Types of the traits in the container. Expressions are resolved by the shape."""
        return self._shape

    def _check_access(self, trait_type: type[Trait]) -> None:
        if not isinstance(trait_type, type) or not issubclass(trait_type, Trait):
            raise TypeError(f'{trait_type!r} is not a subclass of `Trait`.')

    def __getitem__[T: Trait](self, trait_type: type[T]) -> T:
        result = self.get(trait_type)
        if result is None:
            raise KeyError(f'There is no {trait_type.__qualname__} in the container.')
        return result

    @overload
    def get[T: Trait](self, trait_type: type[T]) -> T | None: ...

    @overload
    def get[T: Trait, D](self, trait_type: type[T], default: D) -> T | D: ...

    def get(self, trait_type: type[Trait], default: Any = None) -> Any:
        """Returns the first trait that is an instance of ``trait_type``, or ``default``."""
        self._check_access(trait_type)
        for trait in self._traits:
            if isinstance(trait, trait_type):
                return trait
        return default

    def get_all_traits[T: Trait](self, trait_type: type[T]) -> tuple[T, ...]:
        """Returns every trait that is an instance of ``trait_type``, in order."""
        self._check_access(trait_type)
        return tuple(i for i in self._traits if isinstance(i, trait_type))

    def __contains__(self, trait_type: object) -> bool:
        if not isinstance(trait_type, type) or not issubclass(trait_type, Trait):
            return False
        return self.get(trait_type) is not None

    def __iter__(self) -> Iterator[Trait]:
        return iter(self._traits)

    def __len__(self) -> int:
        return len(self._traits)

    def view(self, declared: Iterable[type[Trait]]) -> TraitsView:
        """A view of this container that answers only for ``declared`` traits."""
        return TraitsView(self, declared)

    def __repr__(self) -> str:
        return f'{type(self).__name__}({", ".join(map(repr, self._traits))})'


class TraitsView(TraitsContainer):
    """A container that answers only for the traits an expression declared.

    It holds only the traits of the original container that are instances of a declared type.
    Asking for a trait type ``T`` is allowed if some declared trait is ``T`` or a subclass of
    ``T``. Asking for anything else raises ``UndeclaredTraitError``, so an expression cannot
    depend on a trait it did not require.
    """

    __slots__ = ('_declared',)

    def __init__(self, container: TraitsContainer, declared: Iterable[type[Trait]]) -> None:
        self._declared = tuple(declared)
        super().__init__(*(i for i in container.traits if isinstance(i, self._declared)))

    @property
    def declared(self) -> tuple[type[Trait], ...]:
        return self._declared

    def _check_access(self, trait_type: type[Trait]) -> None:
        super()._check_access(trait_type)
        if not any(issubclass(i, trait_type) for i in self._declared):
            raise UndeclaredTraitError(trait_type, self._declared)

    def __contains__(self, trait_type: object) -> bool:
        if not isinstance(trait_type, type) or not issubclass(trait_type, Trait):
            return False
        if not any(issubclass(i, trait_type) for i in self._declared):
            return False
        return super().__contains__(trait_type)
