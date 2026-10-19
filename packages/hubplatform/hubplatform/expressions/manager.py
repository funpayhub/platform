from collections import defaultdict
from collections.abc import Sequence, Set

from hubplatform.expressions.catalog import ExpressionsCatalog
from hubplatform.expressions.scope import ExpressionsScope


class ExpressionsManager:
    def __init__(
        self,
        catalog: ExpressionsCatalog | None = None,
    ) -> None:
        self._catalog: ExpressionsCatalog = ExpressionsCatalog() if catalog is None else catalog
        self._root_scope = ExpressionsScope(root=True)
        self._groups: dict[str, list[tuple[str, ...]]] = defaultdict(list)

    def add_group(self, group_id: str, scopes: Set[Sequence[str]]) -> None:
        self._groups[group_id].extend(tuple(i) for i in scopes)

    def add_scope_to_group(
        self,
        group_id: str,
        scope_path: Sequence[str],
        add_group_if_not_exists: bool = True
    ) -> None:
        if not scope_path:
            return

        if group_id not in self._groups and not add_group_if_not_exists:
            return

        if scope_path in self._groups[group_id]:
            return

        self._groups[group_id].append(tuple(scope_path))

    @property
    def groups(self) -> dict[str, list[tuple[str, ...]]]:
        return {k: v.copy() for k, v in self._groups.items()}

    @property
    def root_scope(self) -> ExpressionsScope:
        return self._root_scope
    