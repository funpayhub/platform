from __future__ import annotations


__all__ = [
    'HubPlatformPlugin',
    'HubPlatformPluginActivator',
    'HubPlatformPluginProto',
    'create_hubplatform_plugin_manager',
]


import os
import sys
import inspect
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from abc import ABC, abstractmethod
from pathlib import Path
from collections.abc import Iterable, Sequence
from importlib.metadata import PackageNotFoundError, version as get_package_version

from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.requirements import Requirement

from .state import JsonPluginStateStore
from .types import LoadedPlugin
from .loader import PluginLoader, PluginDiscovery, ClassPluginFactory
from .manager import PluginManager
from .installer import LocalPluginArtifactInstaller
from .repository.fetcher import PluginRepositoryBinding
from .dependencies.manager import DependencyManager
from .dependencies.resolver import PipDependencyResolver
from .dependencies.installer import PipPackageInstaller


if TYPE_CHECKING:
    from hubplatform.app import HubPlatformApp


@runtime_checkable
class HubPlatformPluginProto(Protocol):
    async def install(self, app: HubPlatformApp) -> None: ...


class HubPlatformPlugin(ABC):
    @abstractmethod
    async def install(self, app: HubPlatformApp) -> None:
        pass


class HubPlatformPluginActivator:
    async def activate(
        self,
        plugin: LoadedPlugin[HubPlatformPluginProto],
        app: HubPlatformApp,
    ) -> None:
        await plugin.instance.install(app)


_DEFAULT_PROTECTED_PACKAGES = (
    'hubplatform',
    'aiogram',
    'eventry',
    'fluent-runtime',
    'packaging',
    'pyconfigtree',
    'pydantic',
)


def _is_hubplatform_plugin(value: object) -> bool:
    return isinstance(value, HubPlatformPluginProto) and inspect.iscoroutinefunction(value.install)


def _build_dependency_constraints(
    explicit: Iterable[Requirement | str],
    protected_packages: Iterable[str],
) -> tuple[Requirement, ...]:
    constraints = tuple(
        value if isinstance(value, Requirement) else Requirement(value) for value in explicit
    )
    constrained_names = {canonicalize_name(value.name) for value in constraints}
    result = list(constraints)
    for package_name in protected_packages:
        if canonicalize_name(package_name) in constrained_names:
            continue
        try:
            package_version = get_package_version(package_name)
        except PackageNotFoundError:
            continue
        result.append(Requirement(f'{package_name}=={package_version}'))
    return tuple(result)


def create_hubplatform_plugin_manager(
    app_version: Version | str,
    plugins_path: str | Path | None = None,
    *,
    environments_path: str | Path | None = None,
    state_path: str | Path | None = None,
    dependency_lock_path: str | Path | None = None,
    python_executable: str | Path = Path(sys.executable),
    dependency_constraints: Iterable[Requirement | str] = (),
    protected_packages: Iterable[str] = _DEFAULT_PROTECTED_PACKAGES,
    pip_args: Sequence[str] = (),
    repositories: Sequence[PluginRepositoryBinding] = (),
) -> PluginManager[HubPlatformPluginProto, HubPlatformApp]:
    """Build the default in-process HubPlatform plugin stack."""

    plugins_location = plugins_path
    if plugins_location is None:
        plugins_location = os.environ.get('HUBPLATFORM_PLUGINS_DIR')
    root = Path(plugins_location or Path.cwd() / 'plugins').resolve()

    environments_location = environments_path
    if environments_location is None:
        environments_location = os.environ.get('HUBPLATFORM_PLUGINS_VENV_DIR')
    environments = Path(environments_location or root / '.environments')
    state = Path(state_path or root / 'state.json')
    dependency_lock = Path(dependency_lock_path or root / 'dependencies.lock.json')

    resolver = PipDependencyResolver(
        python_executable=python_executable,
        pip_args=pip_args,
    )
    package_installer = PipPackageInstaller(
        environments_path=environments,
        python_executable=python_executable,
        pip_args=pip_args,
    )
    dependency_manager = DependencyManager(
        resolver=resolver,
        installer=package_installer,
        lock_path=dependency_lock,
        constraints=_build_dependency_constraints(
            dependency_constraints,
            protected_packages,
        ),
    )
    factory = ClassPluginFactory[HubPlatformPluginProto](
        validator=_is_hubplatform_plugin,
        contract_name='HubPlatformPluginProto',
    )
    loader = PluginLoader(factory=factory)
    return PluginManager(
        app_version=app_version,
        discovery=PluginDiscovery(root),
        loader=loader,
        activator=HubPlatformPluginActivator(),
        artifact_installer=LocalPluginArtifactInstaller(root),
        dependency_manager=dependency_manager,
        state_store=JsonPluginStateStore(state),
        repositories=repositories,
    )
