from __future__ import annotations


__all__ = ['DependencyManager', 'global_dependency_manager']

from functools import cache
from collections.abc import Iterable, Sequence

from packaging.requirements import Requirement

from .resolver import DependencyResolver, PipDependencyResolver
from .installer import PackageInstaller, PipPackageInstaller


def _normalize_requirements(requirements: Iterable[Requirement | str]) -> set[Requirement]:
    if not isinstance(requirements, Sequence):
        raise TypeError('Requirements must be a tuple.')
    result = set()
    for i in requirements:
        if isinstance(i, str):
            result.add(Requirement(i))
        elif isinstance(i, Requirement):
            result.add(i)
        else:
            raise TypeError('Each requirement must be a string or Requirement.')
    return result


class DependencyManager:
    def __init__(
        self,
        resolver: DependencyResolver,
        installer: PackageInstaller,
        dependencies: Sequence[Requirement | str] = (),
    ) -> None:
        self._deps: set[Requirement] = set()
        self.add_dependencies(dependencies)
        self._installer = installer
        self._resolver = resolver

    @property
    def installer(self) -> PackageInstaller:
        return self._installer

    @property
    def resolver(self) -> DependencyResolver:
        return self._resolver

    @property
    def current_dependencies(self) -> frozenset[Requirement]:
        return frozenset(self._deps)

    def add_dependencies(self, dependencies: Iterable[Requirement | str]) -> None:
        self._deps.update(_normalize_requirements(dependencies))

    async def install(self, dependencies: Sequence[Requirement]) -> None:
        deps = self._deps.copy() | set(dependencies)
        resolved = await self._resolver.resolve_dependencies([*deps])
        await self._installer.install_packages(resolved)
        self.add_dependencies(deps)


@cache
def global_dependency_manager():
    installer = PipPackageInstaller()
    resolver = PipDependencyResolver()
    return DependencyManager(resolver=resolver, installer=installer)
