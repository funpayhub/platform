from __future__ import annotations


__all__ = [
    'ExpressionsManager',
    'EvaluationResult',
]

from typing import Any
from dataclasses import dataclass
from types import MappingProxyType
from itertools import combinations
from collections.abc import Mapping, Callable, Iterable, Sequence

from hubplatform.logging.loggers import expressions as _logger

from .scope import ExpressionsScope
from ..syntax import Call, StringWithCalls, call_decoder
from ..traits import Trait, TraitsContainer
from .category import (
    CategoryPath,
    ExpressionsCategoryInfo,
    ExpressionsCategoryNode,
    normalize_category_path,
)
from .envelope import ExpressionEnvelope
from ..fragments import Fragment, EvaluatedPart, fragment_to_text
from ..definition import (
    Expression,
    ExpressionCallResult,
    ExpressionDefinition,
    extract_expression_definition,
)
from ..exceptions import (
    ExpressionError,
    UnknownExpressionError,
    AmbiguousExpressionError,
    ExpressionExecutionError,
    ExpressionsConfigurationError,
)
from ..requirement import Requirement


@dataclass(frozen=True)
class EvaluationResult:
    parts: Sequence[EvaluatedPart]
    """
    Text and fragments in text order. Neighbouring text is merged into one string
    and empty strings are dropped, so two strings never follow each other.
    Always stored as a tuple, whatever sequence is passed.
    """
    decoded: StringWithCalls
    errors: Sequence[ExpressionError] = ()
    """Errors of failed calls (only with ``ignore_errors=True``). Always stored as a tuple."""

    def __post_init__(self) -> None:
        object.__setattr__(self, 'errors', tuple(self.errors))

        parts: list[EvaluatedPart] = []
        for part in self.parts:
            if isinstance(part, Fragment):
                parts.append(part)
            elif not isinstance(part, str):
                raise TypeError(
                    f'Evaluation result parts must be strings or fragments, '
                    f'not {type(part).__name__}.'
                )
            elif not part:
                continue
            elif parts and isinstance(parts[-1], str):
                parts[-1] += part
            else:
                parts.append(part)
        object.__setattr__(self, 'parts', tuple(parts))

    @property
    def has_fragments(self) -> bool:
        return any(isinstance(i, Fragment) for i in self.parts)

    @property
    def text(self) -> str:
        """The result as text: fragments are replaced with their text fallbacks."""
        return ''.join(fragment_to_text(i) for i in self.parts)

    def __str__(self) -> str:
        return self.text


class ExpressionsManager:
    """Registers traits and expressions, resolves which expressions are available for a set of
    traits and evaluates texts.

    Each expression declares a ``Requirement``: the trait types a ``TraitsContainer`` must have
    for the expression to be available. Several expressions can be registered under one call key
    with different requirements. For a container, the call key refers to the most specific of the
    expressions whose requirements the container satisfies (see ``Requirement.covers``):

    - An expression that is more specific than another one with the same call key must be
      registered with ``override=True``, and ``override=True`` without a less specific expression
      to override is an error. This prevents an extension from shadowing an expression silently.
    - If several expressions are available and none of them is more specific than all the others,
      calling the key raises ``AmbiguousExpressionError``. ``freeze()`` warns about every pair of
      such expressions that has no override for the traits of both.

    Resolution is cached per container shape (the set of trait types in the container).
    """

    def __init__(self, context: Mapping[str, Any]) -> None:
        self._expressions: dict[str, dict[Requirement, ExpressionEnvelope]] = {}
        self._categories: dict[CategoryPath, ExpressionsCategoryInfo] = {}

        self._trait_to_id: dict[type[Trait], str] = {}
        self._id_to_trait: dict[str, type[Trait]] = {}

        self._categories_tree: ExpressionsCategoryNode = ExpressionsCategoryNode()
        self._scopes: dict[frozenset[type[Trait]], ExpressionsScope] = {}
        self._warnings: tuple[str, ...] = ()

        self._frozen = False
        self._context = context

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def warnings(self) -> tuple[str, ...]:
        """Warnings found by ``freeze()``: pairs of equally specific expressions without an
        override for both. They are also logged."""
        return self._warnings

    @property
    def traits(self) -> Mapping[str, type[Trait]]:
        """Registered trait types by ID, in registration order."""
        return MappingProxyType(self._id_to_trait)

    def get_trait_id(self, trait_type: type[Trait]) -> str:
        """Returns the ID of a registered trait type. Raises ``KeyError`` if it is not
        registered."""
        return self._trait_to_id[trait_type]

    def get_scope(self, traits: TraitsContainer | Iterable[type[Trait]]) -> ExpressionsScope:
        """Returns the expressions available for a container, or for a container that would hold
        traits of the given types. Results are cached by shape."""
        self._check_frozen()
        shape = traits.shape if isinstance(traits, TraitsContainer) else frozenset(traits)
        scope = self._scopes.get(shape)
        if scope is None:
            for trait_type in shape:
                if not isinstance(trait_type, type) or not issubclass(trait_type, Trait):
                    raise TypeError(f'{trait_type!r} is not a subclass of `Trait`.')
            scope = self._resolve(shape)
            self._scopes[shape] = scope
        return scope

    def get_registrations(self, call_key: str) -> tuple[ExpressionEnvelope, ...]:
        """Every expression registered under ``call_key``, whatever its requirement."""
        return tuple(self._expressions.get(call_key, {}).values())

    @property
    def categories(self) -> Mapping[CategoryPath, ExpressionsCategoryInfo]:
        return MappingProxyType(self._categories)

    @property
    def categories_tree(self) -> ExpressionsCategoryNode:
        """Root of the categories tree. Available after freezing."""
        self._check_frozen()
        return self._categories_tree

    def get_category(self, category_path: Sequence[str] = ()) -> ExpressionsCategoryNode:
        """Finds a category node by its path. The empty path is the root.
        Raises `KeyError` if there is no such category."""
        self._check_frozen()
        curr = self._categories_tree
        for category_id in category_path:
            if category_id not in curr.subcategories:
                raise KeyError(f'Category {tuple(category_path)!r} does not exist.')
            curr = curr.subcategories[category_id]
        return curr

    def add_trait(self, trait_type: type[Trait], id: str) -> None:
        """Registers a trait type under an ID. Every trait type that an expression requires must
        be registered. Registered traits are the filters of the documentation UI."""
        self._check_not_frozen()
        if (
            not isinstance(trait_type, type)
            or not issubclass(trait_type, Trait)
            or trait_type is Trait
        ):
            raise TypeError('`trait_type` must be a subclass of `Trait`.')

        if trait_type in self._trait_to_id:
            raise ValueError(
                f"Trait '{trait_type.__module__}.{trait_type.__qualname__}' "
                f'already registered under ID {self._trait_to_id[trait_type]!r}.'
            )

        if id in self._id_to_trait:
            other = self._id_to_trait[id]
            raise ValueError(
                f"ID {id!r} is already acquired by '{other.__module__}.{other.__qualname__}'."
            )

        self._trait_to_id[trait_type] = id
        self._id_to_trait[id] = trait_type

    def add_expression(
        self,
        expression: Expression | ExpressionDefinition,
        call_key: str,
        category: Sequence[str] | None = None,
        override: bool = False,
    ) -> None:
        """Registers an expression. Its requirement is taken from its definition
        (``@expression(requires=...)``).

        :param override: The expression replaces a less specific expression with the same
            call key for containers that satisfy both.
        """
        self._check_not_frozen()
        category_path = None if category is None else normalize_category_path(category)

        definition = (
            expression
            if isinstance(expression, ExpressionDefinition)
            else extract_expression_definition(expression)
        )

        registered = self._expressions.setdefault(call_key, {})
        if definition.requirement in registered:
            raise ValueError(
                f'Call key {call_key!r} already registered for {definition.requirement!r}.'
            )

        registered[definition.requirement] = ExpressionEnvelope(
            expression=definition,
            call_key=call_key,
            category=category_path,
            override=override,
        )

    def register[T: Expression | ExpressionDefinition](
        self,
        *,
        call_key: str,
        category: Sequence[str] | None = None,
        override: bool = False,
    ) -> Callable[[T], T]:
        def inner(expr: T) -> T:
            self.add_expression(
                expression=expr,
                call_key=call_key,
                category=category,
                override=override,
            )
            return expr

        return inner

    def add_category(
        self, category_path: Sequence[str], category: ExpressionsCategoryInfo
    ) -> None:
        self._check_not_frozen()
        path = normalize_category_path(category_path)
        if path in self._categories:
            raise ValueError(f'Category {path!r} is already registered.')
        self._categories[path] = category

    def freeze(self) -> None:
        """Checks the registered expressions and locks the manager.

        Raises ``ExpressionsConfigurationError`` with every problem found (unregistered traits,
        wrong use of ``override``); the manager stays unfrozen in that case. Pairs of equally
        specific expressions without an override for both are logged as warnings and stored in
        ``warnings``.
        """
        if self._frozen:
            return

        problems = [*self._check_traits_are_registered(), *self._check_overrides()]
        if problems:
            raise ExpressionsConfigurationError(problems)

        self._warnings = tuple(self._find_uncovered_pairs())
        for warning in self._warnings:
            _logger.manager.warning(warning)

        self._categories_tree = self._build_categories_tree()
        self._frozen = True

    async def evaluate(
        self,
        string: str,
        traits: TraitsContainer | None = None,
        ignore_errors: bool = False,
    ) -> EvaluationResult:
        """Evaluates ``string`` with ``traits`` and returns it as a sequence of text and fragments.

        Without ``traits``, only expressions without requirements are available.

        Each top-level call is executed once. Its result is rendered with the expression's renderer
        (or ``str()``); a ``Fragment`` returned by the expression or by its renderer is kept as an
        object. The code that sends the result decides how to send each fragment. Where only text
        can be used, take ``result.text``: it replaces fragments with their text fallbacks.

        With ``ignore_errors=True``, a failed call is dropped from the result and its error is
        added to ``errors``. Otherwise the first error is raised.
        """
        traits = TraitsContainer() if traits is None else traits
        decoded = call_decoder.extract_calls(string)
        parts: list[EvaluatedPart] = []
        errors: list[ExpressionError] = []

        for i in decoded.decoded:
            if isinstance(i, str):
                parts.append(i)
                continue

            try:
                part = await self._evaluate_call(i, traits)
            except Exception as err:
                if not isinstance(err, ExpressionExecutionError):
                    new_e = ExpressionExecutionError(expression_id=i.name)
                    new_e.__cause__ = err
                    err = new_e
                if ignore_errors:
                    errors.append(err)
                    continue
                raise err
            parts.append(part)

        return EvaluationResult(parts=parts, errors=errors, decoded=decoded)

    async def _evaluate_call(self, call: Call, traits: TraitsContainer) -> EvaluatedPart:
        """Executes ``call`` once and renders its result into text or a fragment."""
        result = await self.execute_call(call, traits)
        try:
            return await result.render(self._context)
        except Exception as e:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'An error occurred while rendering the result of {call.name!r}.',
            ) from e

    def resolve_call_key(self, call_key: str, traits: TraitsContainer) -> ExpressionEnvelope:
        """Returns the expression that ``call_key`` refers to for ``traits``.

        Raises ``UnknownExpressionError`` or ``AmbiguousExpressionError``.
        """
        scope = self.get_scope(traits)
        if call_key in scope.ambiguous:
            raise AmbiguousExpressionError(call_key, scope.ambiguous[call_key])
        envelope = scope.expressions.get(call_key)
        if envelope is None:
            raise UnknownExpressionError(call_key)
        return envelope

    async def execute_call(self, call: Call, traits: TraitsContainer) -> ExpressionCallResult:
        envelope = self.resolve_call_key(call.name, traits)

        args = [await self.resolve_value(arg, traits) for arg in call.args]
        kwargs = {
            key: await self.resolve_value(value, traits) for key, value in call.kwargs.items()
        }

        try:
            return await envelope.expression.execute(traits, args, kwargs, self._context)
        except Exception as e:
            raise ExpressionExecutionError(
                expression_id=call.name,
                message=f'An error occurred while executing {call.name!r}.',
            ) from e

    async def resolve_value(self, value: Any, traits: TraitsContainer) -> Any:
        if isinstance(value, Call):
            return (await self.execute_call(value, traits)).value

        if isinstance(value, tuple):
            return tuple([await self.resolve_value(item, traits) for item in value])

        if isinstance(value, frozendict):
            return frozendict(
                {key: await self.resolve_value(item, traits) for key, item in value.items()}
            )

        return value

    def _check_not_frozen(self) -> None:
        if self._frozen:
            raise RuntimeError("Operation available only when expressions manager isn't frozen.")

    def _check_frozen(self) -> None:
        if not self._frozen:
            raise RuntimeError('Operation available only when expressions manager is frozen.')

    def _check_traits_are_registered(self) -> list[str]:
        problems: list[str] = []
        for call_key, registered in self._expressions.items():
            for requirement in registered:
                for trait_type in requirement.traits:
                    if trait_type not in self._trait_to_id:
                        problems.append(
                            f'${call_key} requires {trait_type.__module__}.'
                            f'{trait_type.__qualname__}, but this trait is not registered.'
                        )
        return problems

    def _check_overrides(self) -> list[str]:
        """Checks that ``override=True`` is used exactly where an expression is more specific
        than another expression with the same call key."""
        problems: list[str] = []
        for call_key, registered in self._expressions.items():
            for envelope in registered.values():
                overridden = [
                    i.requirement
                    for i in registered.values()
                    if envelope.requirement.is_more_specific_than(i.requirement)
                ]
                if overridden and not envelope.override:
                    problems.append(
                        f'${call_key} for {envelope.requirement!r} overrides ${call_key} for '
                        f'{", ".join(map(repr, overridden))}, but is not registered with '
                        f'`override=True`.'
                    )
                elif envelope.override and not overridden:
                    problems.append(
                        f'${call_key} for {envelope.requirement!r} is registered with '
                        f'`override=True`, but there is no less specific ${call_key} to override.'
                    )
        return problems

    def _find_uncovered_pairs(self) -> list[str]:
        """Pairs of incomparable expressions with the same call key without an expression that
        requires the traits of both. A container with both traits cannot call that key."""
        warnings: list[str] = []
        for call_key, registered in self._expressions.items():
            for a, b in combinations(registered, 2):
                if a.covers(b) or b.covers(a):
                    continue
                if any(i.covers(a) and i.covers(b) for i in registered):
                    continue
                warnings.append(
                    f'${call_key} is ambiguous for traits {a | b!r}: it is registered for '
                    f'{a!r} and {b!r}. Register an override for {a | b!r} if a container can '
                    f'have these traits together.'
                )
        return warnings

    def _resolve(self, shape: frozenset[type[Trait]]) -> ExpressionsScope:
        """Picks the most specific expression for every call key available for ``shape``."""
        expressions: dict[str, ExpressionEnvelope] = {}
        ambiguous: dict[str, list[ExpressionEnvelope]] = {}
        for call_key, registered in self._expressions.items():
            candidates = [i for i in registered.values() if i.requirement.is_satisfied_by(shape)]
            most_specific = [
                i
                for i in candidates
                if not any(j.requirement.is_more_specific_than(i.requirement) for j in candidates)
            ]
            if len(most_specific) == 1:
                expressions[call_key] = most_specific[0]
            elif most_specific:
                ambiguous[call_key] = most_specific
        return ExpressionsScope(shape, expressions, ambiguous)

    def _build_categories_tree(self) -> ExpressionsCategoryNode:
        used = {
            i.category
            for registered in self._expressions.values()
            for i in registered.values()
            if i.category is not None
        }
        paths = [*self._categories, *sorted(used - self._categories.keys())]

        root = ExpressionsCategoryNode()
        for path in paths:
            curr = root
            for i, category_id in enumerate(path, 1):
                if category_id not in curr.subcategories:
                    curr._add_subcategory(
                        ExpressionsCategoryNode(category_id, self._categories.get(path[:i]))
                    )
                curr = curr.subcategories[category_id]
        return root

    def _copy(self) -> ExpressionsManager:
        manager = ExpressionsManager({})
        manager._expressions = {k: v.copy() for k, v in self._expressions.items()}
        manager._categories = self._categories.copy()
        manager._trait_to_id = self._trait_to_id.copy()
        manager._id_to_trait = self._id_to_trait.copy()
        return manager

    def _merge_single(self, manager: ExpressionsManager, skip_existing: bool = True) -> None:
        self._check_not_frozen()
        if not skip_existing:
            for call_key, registered in manager._expressions.items():
                if col := self._expressions.get(call_key, {}).keys() & registered.keys():
                    requirements = ', '.join(map(repr, col))
                    raise RuntimeError(
                        f'Call key {call_key!r} already registered for {requirements}.'
                    )

            if col2 := self._categories.keys() & manager._categories.keys():
                raise RuntimeError(f'Categories {col2!r} already registered.')

            if col3 := self._trait_to_id.keys() & manager._trait_to_id.keys():
                raise RuntimeError(f'Traits {col3!r} already registered.')

            if col4 := self._id_to_trait.keys() & manager._id_to_trait.keys():
                raise RuntimeError(f'Trait IDs {col4} already registered.')

        for call_key, registered in manager._expressions.items():
            own = self._expressions.setdefault(call_key, {})
            own |= {k: v for k, v in registered.items() if k not in own}

        self._categories |= {
            k: v for k, v in manager._categories.items() if k not in self._categories
        }

        ids_to_merge = {k for k in manager._id_to_trait if k not in self._id_to_trait}
        traits_to_merge = {
            k: v
            for k, v in manager._trait_to_id.items()
            if k not in self._trait_to_id and v in ids_to_merge
        }
        self._trait_to_id |= traits_to_merge
        self._id_to_trait |= {v: k for k, v in traits_to_merge.items()}

    def _replace_with(self, manager: ExpressionsManager) -> None:
        self._check_not_frozen()
        self._expressions = manager._expressions
        self._categories = manager._categories
        self._trait_to_id = manager._trait_to_id
        self._id_to_trait = manager._id_to_trait

    def merge_from(self, *managers: ExpressionsManager, skip_existing: bool = True) -> None:
        self._check_not_frozen()
        if not managers:
            return

        candidate = self._copy()
        for manager in managers:
            candidate._merge_single(manager, skip_existing=skip_existing)

        self._replace_with(candidate)
