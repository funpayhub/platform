from collections.abc import Sequence, Set
from copy import deepcopy

from hubplatform.expressions.registry import ExpressionsRegistry
from hubplatform.expressions.scope import ExpressionsScope


class ExpressionsManager:
    def __init__(
        self,
        expressions_registry: ExpressionsRegistry | None = None,
    ) -> None:
        self._registry: ExpressionsRegistry = (
            ExpressionsRegistry() if expressions_registry is None else expressions_registry
        )
        self._scopes: dict[str, ExpressionsScope] = {}
        self._groups: dict[str, set[tuple[str, ...]]] = {}


    def add_scope(self, scope_id: str, scope: ExpressionsScope) -> None:
        if scope_id in self._scopes:
            raise KeyError(f'Scope {scope_id!r} already exists.')  # todo: custom error

        self._scopes[scope_id] = scope

    def add_group(self, group_id: str, scopes: Set[Sequence[str]]) -> None:
        if group_id in self._groups:
            raise KeyError(f'Group {group_id!r} already exists.')

        self._groups[group_id] = {tuple(i) for i in scopes}

    def add_scope_to_group(self, group_id: str, scope_path: Sequence[str]) -> None:
        if not scope_path:
            return

    @property
    def scopes(self) -> dict[str, ExpressionsScope]:
        return self._scopes.copy()

    @property
    def groups(self) -> dict[str, set[tuple[str, ...]]]:
        return {k: v.copy() for k, v in self._groups.items()}

    def get_scope(self, scope_path: Sequence[str]) -> ExpressionsScope | None:
        if not scope_path:
            return None

        if scope_path[0] not in self._scopes:
            return None

        return self._scopes[scope_path[0]].get_subscope(scope_path[1:])

    