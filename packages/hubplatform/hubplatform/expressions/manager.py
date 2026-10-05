from collections.abc import Mapping

from .registry import ExpressionsRegistry
from types import MappingProxyType


class ExpressionRegistriesManager:
    def __init__(
        self,
        common_registry: ExpressionsRegistry | None = None
    ):
        self._common_registry = common_registry if common_registry is not None else ExpressionsRegistry()
        self._registries: dict[str, ExpressionsRegistry] = {}
        self._registries_proxy = MappingProxyType(self._registries)

    def add_registry(self, registry_id: str, registry: ExpressionsRegistry) -> None:
        if registry_id in self._registries:
            raise RuntimeError(f'Registry {registry_id} already registered in manager.')
        self._registries[registry_id] = registry

    def remove_registry(self, registry_id: str) -> ExpressionsRegistry | None:
        return self._registries.pop(registry_id, None)

    @property
    def common_registry(self) -> ExpressionsRegistry | None:
        return self._common_registry

    @property
    def registries(self) -> Mapping[str, ExpressionsRegistry]:
        return self._registries_proxy