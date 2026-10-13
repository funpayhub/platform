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


    def add_scope(self, scope_id: str, scope: ExpressionsScope) -> None:
        if scope_id in self._scopes:
            raise KeyError(f'Scope {scope_id!r} already exists.')  # todo: custom error

        self._scopes[scope_id] = scope
    