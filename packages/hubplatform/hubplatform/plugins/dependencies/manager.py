from __future__ import annotations


__all__ = ['DependencyManager']


import os
import json
import site
import asyncio
import tempfile
import importlib
from pathlib import Path
from collections.abc import Iterable

from packaging.version import Version
from packaging.requirements import Requirement

from .types import Package, DependencyPlan, DependencyEnvironment
from .resolver import DependencyResolver, normalize_requirements
from .installer import PackageInstaller
from ..exceptions import DependencyInstallationError


class DependencyManager:
    """Reconciles the complete desired dependency set with a shared plugin environment."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        resolver: DependencyResolver,
        installer: PackageInstaller,
        lock_path: str | Path,
        *,
        constraints: Iterable[Requirement | str] = (),
    ) -> None:
        self._resolver = resolver
        self._installer = installer
        self._lock_path = Path(lock_path)
        self._constraints = normalize_requirements(constraints)
        self._operation_lock = asyncio.Lock()
        self._current_plan: DependencyPlan | None = None
        self._current_environment: DependencyEnvironment | None = None
        self._active_environment: DependencyEnvironment | None = None

    @property
    def resolver(self) -> DependencyResolver:
        return self._resolver

    @property
    def installer(self) -> PackageInstaller:
        return self._installer

    @property
    def constraints(self) -> tuple[Requirement, ...]:
        return self._constraints

    @property
    def current_plan(self) -> DependencyPlan | None:
        return self._current_plan

    @property
    def current_environment(self) -> DependencyEnvironment | None:
        return self._current_environment

    @property
    def active_environment(self) -> DependencyEnvironment | None:
        return self._active_environment

    async def plan(
        self,
        dependencies: Iterable[Requirement | str],
    ) -> DependencyPlan:
        normalized = normalize_requirements(dependencies)
        locked = self._load_lock()
        if locked is not None:
            locked_plan, _ = locked
            if tuple(map(str, locked_plan.requirements)) == tuple(map(str, normalized)) and tuple(
                map(str, locked_plan.constraints)
            ) == tuple(map(str, self._constraints)):
                return locked_plan
        return await self._resolver.resolve_dependencies(
            normalized,
            constraints=self._constraints,
        )

    async def apply(self, plan: DependencyPlan) -> DependencyEnvironment:
        environment = await self._installer.install_packages(plan)
        self._save_lock(plan, environment)
        self._current_plan = plan
        self._current_environment = environment
        return environment

    async def reconcile(
        self,
        dependencies: Iterable[Requirement | str],
        *,
        activate: bool = False,
    ) -> DependencyEnvironment:
        async with self._operation_lock:
            plan = await self.plan(dependencies)
            locked = self._load_lock()
            if locked is not None and locked[0].fingerprint == plan.fingerprint:
                environment = locked[1]
                if (
                    not environment.site_packages.is_dir()
                    or not (environment.site_packages.parent / 'environment.json').is_file()
                ):
                    environment = await self.apply(plan)
                else:
                    self._current_plan = plan
                    self._current_environment = environment
            else:
                environment = await self.apply(plan)

            if activate:
                self.activate(environment)
                await self._installer.collect_garbage({environment.fingerprint})
            return environment

    def activate(self, environment: DependencyEnvironment) -> None:
        active = self._active_environment
        if active is not None:
            if active.fingerprint == environment.fingerprint:
                return
            raise DependencyInstallationError(
                'A different plugin dependency environment is already active. '
                'Restart the process to activate the new environment.'
            )
        if not environment.site_packages.is_dir():
            raise DependencyInstallationError(
                f'Plugin environment {str(environment.site_packages)!r} does not exist.'
            )
        site.addsitedir(str(environment.site_packages))
        importlib.invalidate_caches()
        self._active_environment = environment

    def _load_lock(self) -> tuple[DependencyPlan, DependencyEnvironment] | None:
        if not self._lock_path.is_file():
            return None
        try:
            raw = json.loads(self._lock_path.read_text(encoding='utf-8'))
            if not isinstance(raw, dict) or raw.get('schema_version') != self.SCHEMA_VERSION:
                return None
            requirements = self._read_requirements(raw.get('requirements'))
            constraints = self._read_requirements(raw.get('constraints'))
            packages = self._read_packages(raw.get('packages'))
            plan = DependencyPlan.create(requirements, constraints, packages)
            fingerprint = raw.get('fingerprint')
            site_packages = raw.get('site_packages')
            if fingerprint != plan.fingerprint or not isinstance(site_packages, str):
                return None
            return plan, DependencyEnvironment(
                fingerprint=plan.fingerprint,
                site_packages=Path(site_packages),
            )
        except (OSError, ValueError, TypeError):
            return None

    def _save_lock(
        self,
        plan: DependencyPlan,
        environment: DependencyEnvironment,
    ) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'schema_version': self.SCHEMA_VERSION,
            'fingerprint': plan.fingerprint,
            'site_packages': str(environment.site_packages),
            'requirements': [str(value) for value in plan.requirements],
            'constraints': [str(value) for value in plan.constraints],
            'packages': [
                {
                    'name': package.name,
                    'version': str(package.version),
                    'install_requirement': package.install_requirement,
                    'hashes': list(package.hashes),
                }
                for package in plan.packages
            ],
        }

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=self._lock_path.parent,
                prefix=f'.{self._lock_path.name}.',
                suffix='.tmp',
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._lock_path)
        except Exception as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise DependencyInstallationError(
                f'Cannot write dependency lock to {str(self._lock_path)!r}.'
            ) from exc

    @staticmethod
    def _read_requirements(value: object) -> tuple[Requirement, ...]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise TypeError('Dependency lock requirements must be a string list.')
        return tuple(Requirement(item) for item in value)

    @staticmethod
    def _read_packages(value: object) -> tuple[Package, ...]:
        if not isinstance(value, list):
            raise TypeError('Dependency lock packages must be a list.')
        packages: list[Package] = []
        for raw_package in value:
            if not isinstance(raw_package, dict):
                raise TypeError('Dependency lock package must be an object.')
            name = raw_package.get('name')
            version = raw_package.get('version')
            install_requirement = raw_package.get('install_requirement')
            hashes = raw_package.get('hashes', [])
            if (
                not isinstance(name, str)
                or not isinstance(version, str)
                or not isinstance(install_requirement, str)
                or not isinstance(hashes, list)
                or not all(isinstance(value, str) for value in hashes)
            ):
                raise TypeError('Dependency lock package is invalid.')
            packages.append(
                Package(
                    name=name,
                    version=Version(version),
                    install_requirement=install_requirement,
                    hashes=tuple(hashes),
                )
            )
        return tuple(packages)
