from __future__ import annotations


__all__ = [
    'ClassPluginFactory',
    'DiscoveryFailure',
    'DiscoveryReport',
    'PluginDiscovery',
    'PluginFactory',
    'PluginLoader',
]


import re
import sys
import hashlib
import importlib
import importlib.util
from typing import Generic, TypeVar, Protocol, cast
from dataclasses import dataclass
from types import ModuleType
from pathlib import Path
from collections.abc import Callable

from pydantic import ValidationError

from .types import LoadedPlugin, DiscoveredPlugin
from .manifest import PluginManifest
from .exceptions import (
    PluginLoadError,
    PluginContractError,
    PluginManifestError,
    PluginDiscoveryError,
)


PluginT = TypeVar('PluginT')
PluginT_co = TypeVar('PluginT_co', covariant=True)


@dataclass(frozen=True)
class DiscoveryFailure:
    path: Path
    error: PluginDiscoveryError


@dataclass(frozen=True)
class DiscoveryReport:
    plugins: tuple[DiscoveredPlugin, ...]
    failures: tuple[DiscoveryFailure, ...]


class PluginDiscovery:
    """Reads manifests without importing plugin code."""

    def __init__(self, plugins_path: str | Path, *, directory_suffix: str = '_plugin') -> None:
        self._plugins_path = Path(plugins_path).resolve()
        self._directory_suffix = directory_suffix

    @property
    def plugins_path(self) -> Path:
        return self._plugins_path

    def discover(self) -> DiscoveryReport:
        if not self._plugins_path.exists():
            return DiscoveryReport(plugins=(), failures=())
        if not self._plugins_path.is_dir():
            error = PluginDiscoveryError(
                f'Plugins path {str(self._plugins_path)!r} is not a directory.'
            )
            return DiscoveryReport(
                plugins=(),
                failures=(DiscoveryFailure(self._plugins_path, error),),
            )

        plugins: list[DiscoveredPlugin] = []
        failures: list[DiscoveryFailure] = []
        seen: dict[str, Path] = {}
        for path in sorted(self._plugins_path.iterdir()):
            if not path.is_dir() or not path.name.endswith(self._directory_suffix):
                continue
            try:
                plugin = self.discover_path(path)
                duplicate_path = seen.get(plugin.manifest.plugin_id)
                if duplicate_path is not None:
                    raise PluginDiscoveryError(
                        f'Plugin id {plugin.manifest.plugin_id!r} is declared by both '
                        f'{str(duplicate_path)!r} and {str(path)!r}.'
                    )
                seen[plugin.manifest.plugin_id] = path
                plugins.append(plugin)
            except PluginDiscoveryError as exc:
                failures.append(DiscoveryFailure(path=path, error=exc))
        return DiscoveryReport(plugins=tuple(plugins), failures=tuple(failures))

    def discover_path(self, path: str | Path) -> DiscoveredPlugin:
        plugin_path = Path(path).resolve()
        if not plugin_path.is_dir():
            raise PluginDiscoveryError(f'Plugin path {str(plugin_path)!r} is not a directory.')

        manifest_path = plugin_path / 'manifest.json'
        if not manifest_path.is_file():
            raise PluginDiscoveryError(
                f'Plugin directory {str(plugin_path)!r} has no manifest.json.'
            )
        try:
            manifest = PluginManifest.model_validate_json(
                manifest_path.read_text(encoding='utf-8')
            )
        except (OSError, UnicodeError, ValidationError, ValueError) as exc:
            raise PluginManifestError(
                f'Cannot load plugin manifest {str(manifest_path)!r}: {exc}'
            ) from exc
        return DiscoveredPlugin(path=plugin_path, manifest=manifest)


class PluginFactory(Protocol[PluginT_co]):
    def create(self, entry_point: object, plugin: DiscoveredPlugin) -> PluginT_co: ...


class ClassPluginFactory(Generic[PluginT]):
    """Instantiates a class entry point and validates the produced object."""

    def __init__(
        self,
        validator: Callable[[object], bool] | None = None,
        *,
        contract_name: str = 'plugin contract',
    ) -> None:
        self._validator = validator
        self._contract_name = contract_name

    def create(self, entry_point: object, plugin: DiscoveredPlugin) -> PluginT:
        if not callable(entry_point):
            raise PluginContractError(
                f'Entry point for plugin {plugin.manifest.plugin_id!r} is not callable.'
            )
        try:
            instance = entry_point()
        except Exception as exc:
            raise PluginLoadError(
                f'Cannot instantiate plugin {plugin.manifest.plugin_id!r}.'
            ) from exc

        if self._validator is not None and not self._validator(instance):
            raise PluginContractError(
                f'Plugin {plugin.manifest.plugin_id!r} does not implement {self._contract_name}.'
            )
        return cast(PluginT, instance)


class PluginLoader(Generic[PluginT]):
    """Imports one plugin under an isolated, deterministic module namespace."""

    def __init__(self, factory: PluginFactory[PluginT]) -> None:
        self._factory = factory

    def load(self, plugin: DiscoveredPlugin) -> LoadedPlugin[PluginT]:
        root_module_name = self._module_name(plugin)
        self._remove_modules(root_module_name)
        importlib.invalidate_caches()

        try:
            self._create_root_module(root_module_name, plugin.path)
            module_name, attribute_name = plugin.manifest.entry_point.rsplit('.', 1)
            module = importlib.import_module(f'{root_module_name}.{module_name}')
            try:
                entry_point = getattr(module, attribute_name)
            except AttributeError as exc:
                raise PluginLoadError(
                    f'Cannot find entry point {plugin.manifest.entry_point!r} for '
                    f'plugin {plugin.manifest.plugin_id!r}.'
                ) from exc
            instance = self._factory.create(entry_point, plugin)
        except PluginLoadError:
            self._remove_modules(root_module_name)
            raise
        except Exception as exc:
            self._remove_modules(root_module_name)
            raise PluginLoadError(
                f'Cannot load plugin {plugin.manifest.plugin_id!r} from {str(plugin.path)!r}.'
            ) from exc

        return LoadedPlugin(
            discovered=plugin,
            instance=instance,
            module_name=root_module_name,
        )

    @staticmethod
    def _module_name(plugin: DiscoveredPlugin) -> str:
        safe_id = re.sub(r'[^a-zA-Z0-9_]', '_', plugin.manifest.plugin_id)
        identity = (
            f'{plugin.manifest.plugin_id}\0{plugin.manifest.plugin_version}\0'
            f'{plugin.path.resolve()}'
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
        return f'_hubplatform_plugin_{safe_id}_{digest}'

    @staticmethod
    def _create_root_module(module_name: str, path: Path) -> ModuleType:
        init_path = path / '__init__.py'
        if init_path.is_file():
            spec = importlib.util.spec_from_file_location(
                module_name,
                init_path,
                submodule_search_locations=[str(path)],
            )
            if spec is None or spec.loader is None:
                raise PluginLoadError(
                    f'Cannot create an import spec for plugin directory {str(path)!r}.'
                )
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module

        module = ModuleType(module_name)
        module.__package__ = module_name
        module.__path__ = [str(path)]
        sys.modules[module_name] = module
        return module

    @staticmethod
    def _remove_modules(root_module_name: str) -> None:
        prefix = f'{root_module_name}.'
        for module_name in tuple(sys.modules):
            if module_name == root_module_name or module_name.startswith(prefix):
                del sys.modules[module_name]
