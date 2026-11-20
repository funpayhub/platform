from __future__ import annotations


__all__ = ['Requirement', 'RequirementLike']

from collections.abc import Iterable

from .traits import Trait


type RequirementLike = Requirement | type[Trait] | Iterable[type[Trait]]
"""A requirement, one trait type or several trait types. No types means no requirement."""


class Requirement:
    """Trait types a container must have for an expression to be available.

    A container satisfies a requirement if, for every required type, it holds a trait of that type
    or of its subclass. An empty requirement is satisfied by every container, including an empty
    one.

    Types are stored in their minimal form: duplicates and types implied by other types (their
    base classes) are dropped, so ``Requirement(FunPayOrderTrait, OrderTrait)`` is
    ``Requirement(FunPayOrderTrait)``. Requirements are compared as sets: the order of types does
    not matter.
    """

    __slots__ = ('_traits', '_set')

    def __init__(self, *traits: type[Trait]) -> None:
        for trait in traits:
            if not isinstance(trait, type) or not issubclass(trait, Trait) or trait is Trait:
                raise TypeError(f'A required trait must be a subclass of `Trait`, not {trait!r}.')

        minimal: list[type[Trait]] = []
        for trait in traits:
            if trait in minimal:
                continue
            if any(i is not trait and issubclass(i, trait) for i in traits):
                continue
            minimal.append(trait)

        self._traits = tuple(minimal)
        self._set = frozenset(minimal)

    @classmethod
    def of(cls, value: RequirementLike) -> Requirement:
        if isinstance(value, Requirement):
            return value
        if isinstance(value, type):
            return cls(value)
        return cls(*value)

    @property
    def traits(self) -> tuple[type[Trait], ...]:
        """The minimal set of required trait types, in the order they were passed."""
        return self._traits

    @property
    def is_empty(self) -> bool:
        """``True`` if every container satisfies this requirement."""
        return not self._traits

    def is_satisfied_by(self, shape: Iterable[type[Trait]]) -> bool:
        """``True`` if a container with traits of these types satisfies the requirement."""
        shape = tuple(shape)
        return all(any(issubclass(i, required) for i in shape) for required in self._traits)

    def covers(self, other: Requirement) -> bool:
        """``True`` if every container that satisfies ``self`` also satisfies ``other``:
        every type of ``other`` is the same as or a base class of some type of ``self``."""
        return all(
            any(issubclass(mine, theirs) for mine in self._traits) for theirs in other._traits
        )

    def is_more_specific_than(self, other: Requirement) -> bool:
        """``True`` if ``self`` covers ``other`` and they are not equal: ``self`` requires
        subclasses of ``other``'s types, more types, or both."""
        return self.covers(other) and not other.covers(self)

    def __or__(self, other: Requirement) -> Requirement:
        """The requirement of a container that satisfies both requirements."""
        return Requirement(*self._traits, *other._traits)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Requirement):
            return NotImplemented
        return self._set == other._set

    def __hash__(self) -> int:
        return hash(self._set)

    def __repr__(self) -> str:
        return f'Requirement({", ".join(i.__qualname__ for i in self._traits)})'
