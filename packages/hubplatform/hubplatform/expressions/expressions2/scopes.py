"""Template vocabularies and declarative selectors for plugin contributions.

Scope inheritance reuses expression bindings and declares which input contracts
an evaluation promises. It does not create Python event/context inheritance.
For FunPay, ``funpay.order`` may extend ``funpay.message`` because its template
vocabulary includes message expressions. Its runtime still supplies independent
values under independent capability keys.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
from types import MappingProxyType
from collections.abc import Mapping

from .catalog import ExpressionDefinition
from .capabilities import Capability


class ScopeSelector(ABC):
    """A pure setup-time predicate over a scope's declared capabilities and tags.

    Selectors describe places where an expression is useful. They never inspect
    an individual order or perform a database lookup. Combining predicates does
    not depend on component IDs or registration order.
    """

    @abstractmethod
    def matches(self, capabilities: frozenset[Capability[Any]], tags: frozenset[str]) -> bool:
        """Return whether a compiled scope should receive a contribution."""

    @property
    def referenced_capabilities(self) -> frozenset[Capability[Any]]:
        """Contracts mentioned by this selector, checked for consistent types."""
        return frozenset()

    def __and__(self, other: ScopeSelector) -> ScopeSelector:
        return _Combined(self, other, 'and')

    def __or__(self, other: ScopeSelector) -> ScopeSelector:
        return _Combined(self, other, 'or')

    def __invert__(self) -> ScopeSelector:
        return _Negated(self)


@dataclass(frozen=True)
class Provides(ScopeSelector):
    """Select scopes promising one particular capability contract."""

    capability: Capability[Any]

    @property
    def referenced_capabilities(self) -> frozenset[Capability[Any]]:
        return frozenset({self.capability})

    def matches(self, capabilities: frozenset[Capability[Any]], tags: frozenset[str]) -> bool:
        return self.capability in capabilities


@dataclass(frozen=True)
class Tagged(ScopeSelector):
    """Select scopes carrying a semantic tag, such as ``marketplace``."""

    tag: str

    def matches(self, capabilities: frozenset[Capability[Any]], tags: frozenset[str]) -> bool:
        return self.tag in tags


@dataclass(frozen=True)
class _Combined(ScopeSelector):
    left: ScopeSelector
    right: ScopeSelector
    operation: str

    @property
    def referenced_capabilities(self) -> frozenset[Capability[Any]]:
        return self.left.referenced_capabilities | self.right.referenced_capabilities

    def matches(self, capabilities: frozenset[Capability[Any]], tags: frozenset[str]) -> bool:
        if self.operation == 'and':
            return self.left.matches(capabilities, tags) and self.right.matches(capabilities, tags)
        return self.left.matches(capabilities, tags) or self.right.matches(capabilities, tags)


@dataclass(frozen=True)
class _Negated(ScopeSelector):
    selector: ScopeSelector

    @property
    def referenced_capabilities(self) -> frozenset[Capability[Any]]:
        return self.selector.referenced_capabilities

    def matches(self, capabilities: frozenset[Capability[Any]], tags: frozenset[str]) -> bool:
        return not self.selector.matches(capabilities, tags)


@dataclass(frozen=True)
class ScopeDefinition:
    """Setup declaration for aliases, input guarantees, and optional vocabulary reuse.

    ``provides`` lists input data the caller must supply. It does not manufacture
    those values. A child inherits its parent's guarantees and must satisfy all
    of them at evaluation time. ``replace`` explicitly authorizes changing an
    inherited alias; silently winning a conflict by registration order is forbidden.
    """

    id: str
    bindings: Mapping[str, str]
    provides: frozenset[Capability[Any]] = frozenset()
    parent: str | None = None
    tags: frozenset[str] = frozenset()
    replace: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'bindings', MappingProxyType(dict(self.bindings)))
        object.__setattr__(self, 'provides', frozenset(self.provides))
        object.__setattr__(self, 'tags', frozenset(self.tags))
        object.__setattr__(self, 'replace', frozenset(self.replace))


@dataclass(frozen=True)
class ScopeContribution:
    """A plugin's aliases to add to every matching current or later scope.

    Contributions are collected during setup and applied at freeze, once all
    plugins and components have registered. They may add names, but cannot change
    a scope's input promises or implicitly override another implementation.
    """

    id: str
    selector: ScopeSelector
    bindings: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'bindings', MappingProxyType(dict(self.bindings)))


@dataclass(frozen=True)
class BoundExpression:
    """A visible template name plus its implementation and registration origin."""

    alias: str
    definition: ExpressionDefinition
    origin: str


@dataclass(frozen=True)
class CompiledScope:
    """Read-only template vocabulary, ready for evaluation or a documentation UI.

    The UI should list these bindings, rather than all global implementation IDs.
    Its displayed ``$message`` documentation will then match the selected scope.
    Categories belong to definition metadata and do not control availability.
    """

    id: str
    bindings: Mapping[str, BoundExpression]
    capabilities: frozenset[Capability[Any]]
    tags: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'bindings', MappingProxyType(dict(self.bindings)))
