"""Typed event data and the short-lived state of one evaluation.

A capability is a named contract for one piece of data. It does not require a
context subclass, and it does not identify a marketplace implementation. For
example, a FunPay sale can supply both a native message and a shared order
reference. An unrelated Playerok sale can supply the same reference contract.

The name distinguishes roles even when their value types are identical:
``CURRENT_ORDER`` and ``REFUNDED_ORDER`` can both contain ``OrderReference``.
Values are always registered explicitly; the engine never searches by type or
guesses capabilities from attributes of an event.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Self, cast, overload
from dataclasses import dataclass
from types import MappingProxyType
from contextvars import ContextVar
from collections.abc import Mapping, Callable, Hashable, Awaitable

from .errors import ExpressionContextError, ExpressionConfigurationError


@dataclass(frozen=True)
class Capability[T]:
    """A stable namespaced key and the runtime type its provider promises.

    Put shared keys in a package that both components and plugins can import.
    Use ordinary concrete classes for ``value_type``. Protocols only work here
    when they support Python's runtime ``isinstance`` checks; type checking
    alone cannot validate the meaning of an order ID or a marketplace name.
    """

    id: str
    value_type: type[T]

    def __post_init__(self) -> None:
        validate_id(self.id, 'Capability')
        if not isinstance(self.value_type, type):
            raise ExpressionConfigurationError('A capability value_type must be a class.')

    def validate(self, value: object) -> None:
        """Reject a value that violates this capability's runtime type contract."""
        try:
            valid = isinstance(value, self.value_type)
        except TypeError as exc:
            raise ExpressionConfigurationError(
                f'Capability {self.id!r} has a type that cannot be checked at runtime.'
            ) from exc
        if not valid:
            raise ExpressionContextError(
                f'Capability {self.id!r} requires {self.value_type.__name__}, '
                f'got {type(value).__name__}.'
            )


def validate_id(value: str, kind: str) -> None:
    """Validate internal IDs independently of the template-name grammar."""
    # Dots, colons, and other namespace separators are valid internal IDs.
    # Template aliases have their own, intentionally narrower validation.
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ExpressionConfigurationError(f'{kind} ID must be nonempty without whitespace.')


def remember_capability(
    definitions: dict[str, Capability[Any]], capability: Capability[Any]
) -> None:
    """Reject incompatible declarations of the same nominal contract."""
    if not isinstance(capability, Capability):
        raise ExpressionConfigurationError('Capability keys must be Capability objects.')
    previous = definitions.get(capability.id)
    if previous is not None and previous.value_type is not capability.value_type:
        raise ExpressionConfigurationError(
            f'Capability {capability.id!r} has conflicting value types: '
            f'{previous.value_type.__name__} and {capability.value_type.__name__}.'
        )
    definitions[capability.id] = capability


class ExpressionRuntime:
    """An immutable mapping of capability keys to values for an event.

    This object contains input data, not caches. It can be reused to render
    several templates: each rendering creates its own EvaluationContext.
    Immutability applies to the mapping, not to native third-party objects.
    Components should avoid changing event objects during a rendering.
    """

    def __init__(self, values: Mapping[Capability[Any], object] | None = None) -> None:
        definitions: dict[str, Capability[Any]] = {}
        copied = dict(values) if values is not None else {}
        for capability, value in copied.items():
            remember_capability(definitions, capability)
            capability.validate(value)
        self._values = MappingProxyType(copied)

    @property
    def capabilities(self) -> frozenset[Capability[Any]]:
        """The explicitly supplied contracts, useful for diagnostics."""
        return frozenset(self._values)

    def require[T](self, capability: Capability[T]) -> T:
        """Read a typed value or explain which event contract is missing."""
        if capability not in self._values:
            raise ExpressionContextError(f'Capability {capability.id!r} was not supplied.')
        return cast(T, self._values[capability])

    def validate(self, expected: frozenset[Capability[Any]]) -> None:
        """Check a selected scope's promises before executing any expression."""
        definitions = {capability.id: capability for capability in expected}
        for capability in self._values:
            remember_capability(definitions, capability)
        for capability in sorted(expected, key=lambda item: item.id):
            self.require(capability)


class EvaluationContext:
    """Runtime input, app services, and a memo table for one rendering.

    Expressions may read capabilities through ``require``. Prefer declaring
    them in a definition's ``requires`` mapping so scopes can be validated at
    setup and documentation can show the requirements. The manager injects
    those dependencies into explicit keyword-only callback parameters.

    ``services`` holds application-lifetime objects such as repositories.
    ``memoize`` holds evaluation-lifetime results such as a fetched stars row.
    Neither belongs in a marketplace context inheritance hierarchy.
    """

    def __init__(
        self,
        runtime: ExpressionRuntime,
        services: Mapping[str, Any] | None = None,
    ) -> None:
        self.runtime = runtime
        self.services: Mapping[str, Any] = MappingProxyType(dict(services or {}))
        self._memo: dict[Hashable, asyncio.Task[Any]] = {}
        self._closed = False
        # A task-local path detects a provider recursively requesting its own
        # memo entry. Without this check that mistake would wait forever.
        self._active: ContextVar[frozenset[Hashable]] = ContextVar(
            'expression_memo_path', default=frozenset()
        )

    def require[T](self, capability: Capability[T]) -> T:
        """Return a capability value with its static type preserved."""
        return self.runtime.require(capability)

    @overload
    async def memoize[T](self, key: Hashable, factory: Callable[[], Awaitable[T]]) -> T: ...

    @overload
    async def memoize[T](self, key: Hashable, factory: Callable[[], T]) -> T: ...

    async def memoize[T](self, key: Hashable, factory: Callable[[], T | Awaitable[T]]) -> T:
        """Compute one value once per rendering, sharing concurrent requests.

        Use a namespaced key that includes every input to the lookup. This is
        explicit caching: the evaluator never caches arbitrary expressions,
        so two calls to ``$random`` still execute independently. Failures are
        removed from the cache so a caller can intentionally retry a lookup.
        """
        if self._closed:
            raise ExpressionContextError('This evaluation context has been closed.')
        if key in self._active.get():
            raise ExpressionContextError(f'Recursive memo lookup for {key!r}.')

        if key not in self._memo:

            async def load_value() -> T:
                token = self._active.set(self._active.get() | {key})
                try:
                    result = factory()
                    if inspect.isawaitable(result):
                        return await result
                    return result
                finally:
                    self._active.reset(token)

            self._memo[key] = asyncio.create_task(load_value())

        task = self._memo[key]
        try:
            # One cancelled waiter must not cancel a value another waiter is
            # using. The manager closes this context and cancels leftovers.
            return cast(T, await asyncio.shield(task))
        except BaseException:
            if task.done() and self._memo.get(key) is task:
                del self._memo[key]
            raise

    async def aclose(self) -> None:
        """Cancel unfinished lookups and release the rendering's memo table."""
        self._closed = True
        tasks = tuple(self._memo.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._memo.clear()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
