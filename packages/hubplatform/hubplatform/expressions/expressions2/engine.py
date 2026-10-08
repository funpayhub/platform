"""Collect definitions during setup, compile scopes, then evaluate templates.

The engine has two phases. Registration permits forward references so component
and plugin setup order is irrelevant. ``freeze`` resolves and validates the
whole configuration atomically. Runtime evaluation only reads that snapshot.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping, Iterable

from hubplatform.expressions.syntax import Call, StringWithCalls
from hubplatform.expressions.syntax.parsing import call_decoder

from .errors import (
    ExpressionError,
    ExpressionsFrozenError,
    ExpressionArgumentError,
    ExpressionNotFoundError,
    ExpressionCollisionError,
    ExpressionExecutionError,
    ExpressionConfigurationError,
)
from .scopes import (
    CompiledScope,
    ScopeSelector,
    BoundExpression,
    ScopeDefinition,
    ScopeContribution,
)
from .catalog import ExpressionCatalog, ExpressionDefinition, validate_alias
from .capabilities import (
    Capability,
    EvaluationContext,
    ExpressionRuntime,
    validate_id,
    remember_capability,
)


@dataclass(frozen=True)
class FormattingResult:
    """Rendered text, its parsed input, and recoverable evaluation failures."""

    result_text: str
    decoded: StringWithCalls
    errors: tuple[ExpressionError, ...] = ()

    def __str__(self) -> str:
        return self.result_text


class ExpressionsManager:
    """Own an application's catalog, scope declarations, and expression engine.

    Register components and plugin contributions during app setup, then call
    ``freeze`` after all component extensions have been installed. The existing
    HubPlatformApp can later own this object; this standalone implementation does
    not change the old application's wiring.

    A scope's capability set is a promise made by its event adapter. The runtime
    must satisfy the complete promise even if a particular template only uses
    ``$upper``. Choose a smaller scope when only common expressions are needed.
    """

    def __init__(
        self,
        *,
        catalog: ExpressionCatalog | None = None,
        services: Mapping[str, Any] | None = None,
        max_depth: int = 64,
    ) -> None:
        if max_depth < 1:
            raise ValueError('max_depth must be positive.')
        self.catalog = catalog if catalog is not None else ExpressionCatalog()
        self._services = dict(services or {})
        self._definitions: dict[str, ScopeDefinition] = {}
        self._contributions: dict[str, ScopeContribution] = {}
        self._compiled: Mapping[str, CompiledScope] | None = None
        self._max_depth = max_depth

    @property
    def frozen(self) -> bool:
        """Whether a successfully compiled, immutable configuration is installed."""
        return self._compiled is not None

    @property
    def scopes(self) -> Mapping[str, CompiledScope]:
        """Compiled vocabularies for evaluators, editors, and documentation UIs."""
        if self._compiled is None:
            raise ExpressionConfigurationError('Call freeze() before reading compiled scopes.')
        return self._compiled

    def _check_mutable(self) -> None:
        if self.frozen:
            raise ExpressionsFrozenError('Expressions manager is frozen.')

    def provide_service(self, id: str, value: object) -> None:
        """Add an application-lifetime service during component/plugin setup.

        Use namespaced names for plugin services. These values can be read from
        ctx.services but never participate in template argument binding. A
        callback can alternatively capture a typed service in a setup closure.
        """
        self._check_mutable()
        validate_id(id, 'Service')
        if id in self._services:
            raise ExpressionConfigurationError(f'Service {id!r} already exists.')
        self._services[id] = value

    def add_scope(
        self,
        id: str,
        *,
        bindings: Mapping[str, str] | None = None,
        provides: Iterable[Capability[Any]] = (),
        parent: str | None = None,
        tags: Iterable[str] = (),
        replace: Iterable[str] = (),
    ) -> None:
        """Declare a vocabulary; referenced parents and expressions may arrive later.

        Bindings map bare template names (``order``) to internal implementation
        IDs (``funpay.order``). A child inherits its parent's bindings, tags, and
        capabilities. Changing an inherited name requires ``replace={'name'}``.
        """
        self._check_mutable()
        validate_id(id, 'Scope')
        if id in self._definitions:
            raise ExpressionConfigurationError(f'Scope {id!r} already exists.')
        if parent is not None:
            validate_id(parent, 'Parent scope')
        definition = ScopeDefinition(
            id=id,
            bindings=bindings or {},
            provides=frozenset(provides),
            parent=parent,
            tags=frozenset(tags),
            replace=frozenset(replace),
        )
        self._validate_bindings(definition.bindings)
        if definition.replace - definition.bindings.keys():
            raise ExpressionConfigurationError('Every replaced alias needs a new binding.')
        self._definitions[id] = definition

    def contribute(self, id: str, *, selector: ScopeSelector, bindings: Mapping[str, str]) -> None:
        """Register a plugin's names once for every matching scope.

        Use ``Provides(ORDER_REFERENCE)`` to extend order scopes independently
        of their component IDs. Rules can precede scopes and expressions; all
        references are checked together at freeze. Runtime data cannot cause a
        rule to attach or detach an expression halfway through a rendering.
        """
        self._check_mutable()
        validate_id(id, 'Contribution')
        if id in self._contributions:
            raise ExpressionConfigurationError(f'Contribution {id!r} already exists.')
        if not isinstance(selector, ScopeSelector):
            raise ExpressionConfigurationError('A contribution needs a ScopeSelector.')
        self._validate_bindings(bindings)
        self._contributions[id] = ScopeContribution(id, selector, bindings)

    @staticmethod
    def _validate_bindings(bindings: Mapping[str, str]) -> None:
        for alias, expression_id in bindings.items():
            validate_alias(alias)
            validate_id(expression_id, 'Expression')

    def freeze(self) -> None:
        """Resolve inheritance and contributions; reject invalid configurations.

        Compilation uses local copies. A failed freeze leaves the manager open
        for missing definitions to be registered and the freeze retried. An
        already frozen manager can safely receive repeated freeze calls.
        """
        if self.frozen:
            return

        contracts: dict[str, Capability[Any]] = {}
        for expression in self.catalog.definitions.values():
            for capability in expression.capabilities:
                remember_capability(contracts, capability)
        for scope_definition in self._definitions.values():
            for capability in scope_definition.provides:
                remember_capability(contracts, capability)
        for contribution in self._contributions.values():
            for capability in contribution.selector.referenced_capabilities:
                remember_capability(contracts, capability)
            # Even an unmatched contribution must not reference a nonexistent
            # implementation. A misspelled ID should fail at setup, not later
            # when someone installs a component that first matches the rule.
            for expression_id in contribution.bindings.values():
                self._get_definition(expression_id)

        base: dict[str, CompiledScope] = {}
        active: list[str] = []

        def compile_base(id: str) -> CompiledScope:
            if id in base:
                return base[id]
            if id in active:
                path = ' -> '.join([*active[active.index(id) :], id])
                raise ExpressionConfigurationError(f'Scope inheritance cycle: {path}.')
            spec = self._definitions.get(id)
            if spec is None:
                raise ExpressionConfigurationError(f'Parent scope {id!r} does not exist.')
            active.append(id)
            bindings: dict[str, BoundExpression] = {}
            capabilities = spec.provides
            tags = spec.tags
            if spec.parent is not None:
                parent = compile_base(spec.parent)
                bindings.update(parent.bindings)
                capabilities |= parent.capabilities
                tags |= parent.tags
            for alias, expression_id in spec.bindings.items():
                if alias in spec.replace and alias not in bindings:
                    raise ExpressionConfigurationError(
                        f'Scope {id!r} cannot replace absent inherited name {alias!r}.'
                    )
                self._bind(
                    id, bindings, alias, expression_id, f'scope:{id}', alias in spec.replace
                )
            self._check_requirements(id, bindings, capabilities)
            result = CompiledScope(id, bindings, capabilities, tags)
            base[id] = result
            active.pop()
            return result

        for id in sorted(self._definitions):
            compile_base(id)

        compiled: dict[str, CompiledScope] = {}
        for id, scope in base.items():
            bindings = dict(scope.bindings)
            # Contributions inspect each flattened BASE scope. They neither
            # change guarantees nor leak from a parent into a nonmatching child
            # (important for selectors containing negation).
            for contribution_id in sorted(self._contributions):
                contribution = self._contributions[contribution_id]
                if contribution.selector.matches(scope.capabilities, scope.tags):
                    for alias, expression_id in contribution.bindings.items():
                        self._bind(
                            id, bindings, alias, expression_id, f'contribution:{contribution.id}'
                        )
            self._check_requirements(id, bindings, scope.capabilities)
            compiled[id] = CompiledScope(id, bindings, scope.capabilities, scope.tags)

        # Publish only after every scope has passed. No renderer can observe a
        # partly compiled vocabulary or definitions changing beneath it.
        self.catalog.freeze()
        self._compiled = MappingProxyType(compiled)

    def _get_definition(self, expression_id: str) -> ExpressionDefinition:
        definition = self.catalog.definitions.get(expression_id)
        if definition is None:
            raise ExpressionConfigurationError(f'Expression {expression_id!r} does not exist.')
        return definition

    def _bind(
        self,
        scope_id: str,
        bindings: dict[str, BoundExpression],
        alias: str,
        expression_id: str,
        origin: str,
        replace: bool = False,
    ) -> None:
        definition = self._get_definition(expression_id)
        previous = bindings.get(alias)
        if previous is not None and not replace:
            if previous.definition.id == expression_id:
                return  # Repeated imports of the exact same binding are idempotent.
            raise ExpressionCollisionError(
                f'Name {alias!r} in scope {scope_id!r} refers to both '
                f'{previous.definition.id!r} ({previous.origin}) and '
                f'{expression_id!r} ({origin}). Rename a binding or explicitly replace it.'
            )
        bindings[alias] = BoundExpression(alias, definition, origin)

    @staticmethod
    def _check_requirements(
        id: str,
        bindings: Mapping[str, BoundExpression],
        capabilities: frozenset[Capability[Any]],
    ) -> None:
        for binding in bindings.values():
            if missing := binding.definition.capabilities - capabilities:
                names = ', '.join(sorted(capability.id for capability in missing))
                raise ExpressionConfigurationError(
                    f'Expression {binding.definition.id!r} bound as ${binding.alias} in '
                    f'scope {id!r} requires capabilities the scope does not provide: {names}.'
                )

    def get_scope(self, id: str) -> CompiledScope:
        """Get the exact visible vocabulary used by a particular template editor."""
        try:
            return self.scopes[id]
        except KeyError as exc:
            raise ExpressionConfigurationError(f'Scope {id!r} does not exist.') from exc

    async def format_text(
        self,
        scope_id: str,
        text: str,
        runtime: ExpressionRuntime | None = None,
        *,
        ignore_errors: bool = False,
    ) -> FormattingResult:
        """Render top-level calls; nested arguments keep their native values.

        Recoverable errors preserve the EXACT source call, including whitespace.
        Parsing errors and broken scope input contracts always raise: ignoring
        expression failures cannot repair invalid syntax or a broken event adapter.
        Generated output is never parsed again, so a buyer's ``$...`` text cannot
        turn into an additional expression call.
        """
        scope = self.get_scope(scope_id)
        inputs = runtime if runtime is not None else ExpressionRuntime()
        inputs.validate(scope.capabilities)
        decoded = call_decoder.extract_calls(text)
        errors: list[ExpressionError] = []
        result: list[str] = []
        spans = iter(decoded.call_spans)
        async with EvaluationContext(inputs, self._services) as ctx:
            for segment in decoded.decoded:
                if isinstance(segment, str):
                    result.append(segment)
                    continue
                start, end = next(spans)
                try:
                    rendered = await self._execute_call(scope, segment, ctx, 0, render=True)
                    result.append(rendered)
                except ExpressionError as exc:
                    exc.span = (start, end)
                    if not ignore_errors:
                        raise
                    errors.append(exc)
                    result.append(text[start:end])
        return FormattingResult(''.join(result), decoded, tuple(errors))

    async def evaluate_call(
        self, scope_id: str, call: Call, runtime: ExpressionRuntime | None = None
    ) -> Any:
        """Evaluate a parsed/programmatic call and return its unrendered value."""
        scope = self.get_scope(scope_id)
        inputs = runtime if runtime is not None else ExpressionRuntime()
        inputs.validate(scope.capabilities)
        async with EvaluationContext(inputs, self._services) as ctx:
            return await self._execute_call(scope, call, ctx, 0)

    async def _execute_call(
        self,
        scope: CompiledScope,
        call: Call,
        ctx: EvaluationContext,
        depth: int,
        *,
        render: bool = False,
    ) -> Any:
        self._check_depth(depth)
        binding = scope.bindings.get(call.name)
        if binding is None:
            raise ExpressionNotFoundError(
                f'Expression ${call.name} is not available in scope {scope.id!r}.',
                alias=call.name,
                scope_id=scope.id,
            )
        try:
            args = [await self._resolve(scope, value, ctx, depth + 1) for value in call.args]
            kwargs = {
                name: await self._resolve(scope, value, ctx, depth + 1)
                for name, value in call.kwargs.items()
            }
            value = await binding.definition.evaluate(ctx, args, kwargs)
            if render:
                return await binding.definition.render(ctx, value)
            return value
        except ExpressionError as exc:
            # Keep the innermost failing call's identity when a nested call
            # propagates outward. The top-level formatter attaches its span.
            if exc.alias is None:
                exc.alias = call.name
                if exc.expression_id is None:
                    exc.expression_id = binding.definition.id
            if exc.scope_id is None:
                exc.scope_id = scope.id
            raise
        except Exception as exc:
            raise ExpressionExecutionError(
                f'Expression ${call.name} ({binding.definition.id!r}) failed '
                f'in scope {scope.id!r}: {exc}',
                expression_id=binding.definition.id,
                alias=call.name,
                scope_id=scope.id,
            ) from exc

    async def _resolve(
        self, scope: CompiledScope, value: Any, ctx: EvaluationContext, depth: int
    ) -> Any:
        self._check_depth(depth)
        if isinstance(value, Call):
            return await self._execute_call(scope, value, ctx, depth)
        if isinstance(value, (list, tuple)):
            return [await self._resolve(scope, item, ctx, depth + 1) for item in value]
        if isinstance(value, dict):
            return {
                key: await self._resolve(scope, item, ctx, depth + 1)
                for key, item in value.items()
            }
        return value

    def _check_depth(self, depth: int) -> None:
        if depth > self._max_depth:
            raise ExpressionArgumentError(
                f'Expression nesting exceeds the configured limit of {self._max_depth}.'
            )
