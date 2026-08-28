from __future__ import annotations

import sys
import importlib
from typing import Any, NoReturn
from dataclasses import dataclass
from copy import copy
from enum import Enum, auto
from pathlib import Path
from collections.abc import Set
from importlib.metadata import PackageNotFoundError, version as get_package_version

from packaging.version import Version
from packaging.requirements import Requirement

from hubplatform.plugins import PluginManifest


class LoaderState(Enum):
    CREATED = auto()
    DISCOVERED = auto()
    VALIDATED = auto()
    LOADED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class DiscoveredPlugin:
    path: Path
    manifest: PluginManifest


@dataclass(frozen=True)
class LoadedPlugin:
    path: Path
    manifest: PluginManifest
    plugin_instance: object

    @classmethod
    def from_discovered_plugin(
        cls, discovered: DiscoveredPlugin, plugin_instance: object
    ) -> LoadedPlugin:
        return cls(
            path=discovered.path,
            manifest=discovered.manifest,
            plugin_instance=plugin_instance,
        )


class PluginsLoader:
    def __init__(
        self,
        app_version: Version | str,
        plugins_path: str | Path = Path('plugins'),
        disabled_plugins: Set[str] = frozenset(),
    ) -> None:
        self._app_version = (
            app_version if isinstance(app_version, Version) else Version(app_version)
        )
        self._plugins_path = Path(plugins_path)
        self._state = LoaderState.CREATED
        self._disabled_plugins = copy(disabled_plugins)

        self._discovered_plugins: dict[str, DiscoveredPlugin] = {}
        self._validated_plugins: dict[str, DiscoveredPlugin] = {}
        self._loaded_plugins: dict[str, LoadedPlugin] = {}

        sys.path.append(str(plugins_path))

    @property
    def app_version(self) -> Version:
        return self._app_version

    @property
    def plugins_path(self) -> Path:
        return self._plugins_path

    @property
    def state(self) -> LoaderState:
        return self._state

    @property
    def disabled_plugins(self) -> Set[str]:
        return self._disabled_plugins

    def discover_plugins(self) -> None:
        self._ensure_state(LoaderState.CREATED)

        for subpath in self._plugins_path.iterdir():
            if not subpath.name.endswith('_plugin') or not subpath.is_dir():
                continue

            manifest_path = subpath / 'manifest.json'
            if not manifest_path.is_file():
                continue  # or raise?

            manifest = self._load_manifest(manifest_path)

            if manifest.plugin_id in self._discovered_plugins:
                self._error(RuntimeError('plugin duplicate.'))  # todo: custom error

            self._discovered_plugins[manifest.plugin_id] = DiscoveredPlugin(
                path=subpath, manifest=manifest
            )

        self._state = LoaderState.DISCOVERED

    def _load_manifest(self, path: Path) -> PluginManifest:
        with open(path, 'r', encoding='utf-8') as f:
            manifest = PluginManifest.model_validate_json(f.read())
        return manifest

    def validate_plugins(self) -> None:
        self._ensure_state(LoaderState.DISCOVERED)

        for plugin_id, plugin in self._discovered_plugins.items():
            if plugin.manifest.plugin_id in self._disabled_plugins:
                continue

            if self._app_version not in plugin.manifest.app_version:
                err = RuntimeError(
                    f'Plugin {plugin_id} requires app version {plugin.manifest.app_version}, '
                    f'but current version is {self._app_version}'
                )  # todo: custom error
                self._error(err)

            for requirement in plugin.manifest.dependencies:
                self._check_requirement_satisfied(requirement, plugin_id)

            self._validated_plugins[plugin_id] = plugin
        self._state = LoaderState.VALIDATED

    def _check_requirement_satisfied(self, requirement: Requirement, plugin_id: str) -> None:
        if requirement.marker is not None and not requirement.marker.evaluate():
            return

        try:
            installed_version = Version(get_package_version(requirement.name))
        except PackageNotFoundError:
            # todo: custom error
            err = RuntimeError(
                f'Plugin {plugin_id} requires package {requirement}, but it is not installed.'
            )
            self._error(err)

        if installed_version not in requirement.specifier:
            err = RuntimeError(
                f'Plugin {plugin_id} requires package {requirement}, '
                f'but version {installed_version} installed.'
            )
            self._error(err)

    def load_plugins(self) -> None:
        self._ensure_state(LoaderState.VALIDATED)

        for plugin_id, plugin in self._validated_plugins.items():
            result = self._load_plugin(plugin)
            self._loaded_plugins[plugin_id] = result

        self._state = LoaderState.LOADED

    def _load_plugin(self, plugin: DiscoveredPlugin) -> LoadedPlugin:
        plugin_module_name = plugin.path.name
        module_name, class_name = plugin.manifest.entry_point.rsplit('.', 1)
        module = importlib.import_module(f'{plugin_module_name}.{module_name}')
        plugin_cls: Any = getattr(module, class_name, None)

        if plugin_cls is None:
            self._error(RuntimeError('Cannot find plugins entry point'))  # todo: custom error

        try:
            instance = plugin_cls()
        except Exception as e:
            err = RuntimeError(
                f'Cannot instantiate plugin {plugin.manifest.plugin_id!r} '
                f"('{plugin_module_name}.{module_name}')."
            )  # todo: custom error
            self._error(err, e)

        return LoadedPlugin.from_discovered_plugin(plugin, instance)

    def _error(self, exc: Exception, from_: Exception | None = None) -> NoReturn:
        self._state = LoaderState.FAILED
        raise exc from from_

    def _ensure_state(self, state: LoaderState) -> None:
        if self._state is not state:
            raise RuntimeError(
                f'Required state for this operation is {state!r}, '
                f'but current state is {self._state!r}.'
            )
