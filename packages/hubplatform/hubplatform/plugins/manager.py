from __future__ import annotations


__all__ = ['PluginManager']


import asyncio
import inspect
from typing import Generic, TypeVar
from dataclasses import replace
from types import MappingProxyType
from collections.abc import Mapping, Callable, Sequence

from packaging.version import Version
from packaging.requirements import Requirement

from .state import PluginStateStore
from .types import (
    LoadedPlugin,
    PluginRecord,
    PluginFailure,
    PluginSnapshot,
    DiscoveredPlugin,
    PluginFailureStage,
    PluginRuntimeState,
    PluginOperationResult,
)
from .loader import PluginLoader, PluginDiscovery, DiscoveryFailure
from .control import PluginStateListener
from .activator import PluginActivator
from .installer import PluginArtifact, PreparedPluginArtifact, PluginArtifactInstaller
from .exceptions import (
    PluginError,
    PluginStateError,
    PluginActivationError,
    PluginDependencyError,
)
from .repository.base import PluginsRepository
from .repository.fetcher import PluginRepositoryBinding
from .dependencies.manager import DependencyManager


PluginT = TypeVar('PluginT')
AppT = TypeVar('AppT')


class PluginManager(Generic[PluginT, AppT]):
    """Long-lived coordinator and the single source of runtime plugin state."""

    def __init__(
        self,
        app_version: Version | str,
        discovery: PluginDiscovery,
        loader: PluginLoader[PluginT],
        activator: PluginActivator[PluginT, AppT],
        artifact_installer: PluginArtifactInstaller,
        dependency_manager: DependencyManager,
        state_store: PluginStateStore,
        repositories: Sequence[PluginRepositoryBinding] = (),
    ) -> None:
        self._app_version = (
            app_version if isinstance(app_version, Version) else Version(app_version)
        )
        self._discovery = discovery
        self._loader = loader
        self._activator = activator
        self._artifact_installer = artifact_installer
        self._dependency_manager = dependency_manager
        self._state_store = state_store
        self._repository_bindings: dict[str, PluginRepositoryBinding] = {}
        for binding in repositories:
            repository_id = binding.repository.repository_id
            if repository_id in self._repository_bindings:
                raise ValueError(f'Duplicate plugin repository {repository_id!r}.')
            self._repository_bindings[repository_id] = binding

        self._records: dict[str, PluginRecord] = {}
        self._candidates: dict[str, DiscoveredPlugin] = {}
        self._snapshots: dict[str, PluginSnapshot] = {}
        self._loaded_plugins: dict[str, LoadedPlugin[PluginT]] = {}
        self._active_plugins: set[str] = set()
        self._discovery_failures: tuple[DiscoveryFailure, ...] = ()
        self._listeners: list[PluginStateListener] = []
        self._operation_lock = asyncio.Lock()
        self._initialized = False
        self._started = False

    @property
    def app_version(self) -> Version:
        return self._app_version

    @property
    def snapshots(self) -> Mapping[str, PluginSnapshot]:
        return MappingProxyType(self._snapshots.copy())

    @property
    def repositories(self) -> Mapping[str, PluginsRepository]:
        return MappingProxyType(
            {
                repository_id: binding.repository
                for repository_id, binding in self._repository_bindings.items()
            }
        )

    @property
    def discovery_failures(self) -> tuple[DiscoveryFailure, ...]:
        return self._discovery_failures

    @property
    def loaded_plugins(self) -> Mapping[str, LoadedPlugin[PluginT]]:
        return MappingProxyType(self._loaded_plugins.copy())

    def subscribe(self, listener: PluginStateListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    async def refresh(self) -> Mapping[str, PluginSnapshot]:
        async with self._operation_lock:
            self._refresh_inventory()
            result = self.snapshots
        await self._publish()
        return result

    async def startup(self, app: AppT) -> Mapping[str, PluginSnapshot]:
        """Restore, reconcile, load and activate plugins before ``app.setup()``."""

        async with self._operation_lock:
            if self._started:
                raise PluginStateError('Plugin manager has already been started.')
            self._refresh_inventory()
            await self._finalize_pending_removals()
            self._refresh_inventory()
            await self._artifact_installer.collect_garbage(
                tuple(record.path for record in self._records.values())
            )

            order, graph_failures = self._activation_plan(self._records, self._candidates)
            self._apply_failures(graph_failures)
            if order:
                requirements = self._requirements_for_order(order, self._candidates)
            else:
                requirements = ()

            dependencies_ready = True
            try:
                await self._dependency_manager.reconcile(requirements, activate=True)
            except Exception as exc:
                dependencies_ready = False
                failure = PluginFailure.from_exception(
                    PluginFailureStage.DEPENDENCIES,
                    exc,
                )
                for plugin_id in order:
                    self._set_runtime_state(
                        plugin_id,
                        PluginRuntimeState.FAILED,
                        failure=failure,
                    )

            if dependencies_ready:
                for plugin_id in order:
                    candidate = self._candidates[plugin_id]
                    inactive_dependency = next(
                        (
                            dependency.plugin_id
                            for dependency in candidate.manifest.plugin_dependencies
                            if dependency.plugin_id not in self._active_plugins
                        ),
                        None,
                    )
                    if inactive_dependency is not None:
                        self._set_runtime_state(
                            plugin_id,
                            PluginRuntimeState.FAILED,
                            failure=PluginFailure(
                                stage=PluginFailureStage.ACTIVATION,
                                message=(
                                    f'Required plugin {inactive_dependency!r} was not activated.'
                                ),
                            ),
                        )
                        continue

                    try:
                        loaded = self._loader.load(candidate)
                        self._loaded_plugins[plugin_id] = loaded
                        self._set_runtime_state(plugin_id, PluginRuntimeState.LOADED)
                    except Exception as exc:
                        self._set_runtime_state(
                            plugin_id,
                            PluginRuntimeState.FAILED,
                            failure=PluginFailure.from_exception(
                                PluginFailureStage.LOADING,
                                exc,
                            ),
                        )
                        continue

                    try:
                        await self._activator.activate(loaded, app)
                    except Exception as exc:
                        activation_error = PluginActivationError(
                            f'Cannot activate plugin {plugin_id!r}.'
                        )
                        activation_error.__cause__ = exc
                        self._set_runtime_state(
                            plugin_id,
                            PluginRuntimeState.FAILED,
                            failure=PluginFailure.from_exception(
                                PluginFailureStage.ACTIVATION,
                                activation_error,
                            ),
                        )
                        continue

                    self._active_plugins.add(plugin_id)
                    self._set_runtime_state(plugin_id, PluginRuntimeState.ACTIVE)

            self._clear_pending_restart()
            self._started = True
            result = self.snapshots
        await self._publish()
        return result

    async def install(
        self,
        artifact: PluginArtifact,
        *,
        enable: bool = True,
    ) -> PluginOperationResult:
        prepared: PreparedPluginArtifact | None = None
        try:
            async with self._operation_lock:
                self._ensure_initialized()
                prepared = await self._artifact_installer.prepare(artifact)
                candidate = prepared.plugin
                self._validate_app_version(candidate)
                plugin_id = candidate.manifest.plugin_id

                records = self._records.copy()
                candidates = self._candidates.copy()
                previous_record = records.get(plugin_id)
                pending_record = PluginRecord(
                    plugin_id=plugin_id,
                    plugin_version=candidate.manifest.plugin_version,
                    path=candidate.path,
                    enabled=enable,
                    pending_restart=True,
                    source=artifact.source or str(artifact.path.resolve()),
                    sha256=prepared.sha256,
                )
                records[plugin_id] = pending_record
                candidates[plugin_id] = candidate

                baseline_order, baseline_failures = self._activation_plan(
                    self._records,
                    self._candidates,
                )
                del baseline_order
                baseline_failures = {
                    **baseline_failures,
                    **self._installed_dependency_failures(
                        self._records,
                        self._candidates,
                    ),
                }
                if enable:
                    records = self._enable_dependency_closure(
                        plugin_id,
                        records,
                        candidates,
                    )

                order, failures = self._activation_plan(records, candidates)
                failures = {
                    **failures,
                    **self._installed_dependency_failures(records, candidates),
                }
                new_failures = set(failures) - set(baseline_failures)
                if plugin_id in failures or (enable and plugin_id not in order):
                    failure = failures.get(plugin_id)
                    raise PluginDependencyError(
                        failure.message if failure is not None else 'Plugin cannot be enabled.'
                    )
                if new_failures:
                    details = ', '.join(sorted(new_failures))
                    raise PluginDependencyError(
                        f'Installing {plugin_id!r} would break enabled plugins: {details}.'
                    )

                requirements = self._requirements_for_order(order, candidates)
                await self._dependency_manager.reconcile(requirements, activate=False)
                installed = await self._artifact_installer.commit(prepared)
                prepared = None

                records[plugin_id] = replace(
                    records[plugin_id],
                    path=installed.plugin.path,
                    plugin_version=installed.plugin.manifest.plugin_version,
                    source=installed.source,
                    sha256=installed.sha256,
                )
                candidates[plugin_id] = installed.plugin
                self._records = records
                self._candidates = candidates
                self._state_store.save(self._records)
                self._refresh_inventory()
                snapshot = self._snapshots[plugin_id]

                if previous_record is not None and previous_record.path == snapshot.record.path:
                    snapshot = replace(
                        snapshot, record=replace(snapshot.record, pending_restart=False)
                    )
                    self._records[plugin_id] = snapshot.record
                    self._snapshots[plugin_id] = snapshot
                    self._state_store.save(self._records)

                result = PluginOperationResult(
                    plugin_id=plugin_id,
                    restart_required=snapshot.restart_required,
                    snapshot=snapshot,
                )
        finally:
            if prepared is not None:
                await self._artifact_installer.discard(prepared)

        await self._publish()
        return result

    async def install_from_repository(
        self,
        repository_id: str,
        plugin_id: str,
        plugin_version: Version | str | None = None,
        *,
        enable: bool = True,
    ) -> PluginOperationResult:
        try:
            binding = self._repository_bindings[repository_id]
        except KeyError as exc:
            raise PluginStateError(
                f'Plugin repository {repository_id!r} is not configured.'
            ) from exc

        if plugin_version is None:
            details = await binding.repository.get_plugin(plugin_id, self._app_version)
            releases = tuple(
                release for release in details.releases if release.plugin_id == plugin_id
            )
            if not releases:
                raise PluginStateError(
                    f'Repository {repository_id!r} has no compatible release for '
                    f'plugin {plugin_id!r}.'
                )
            release = max(releases, key=lambda value: value.plugin_version)
        else:
            version = (
                plugin_version if isinstance(plugin_version, Version) else Version(plugin_version)
            )
            release = await binding.repository.get_release(plugin_id, version)

        if release.plugin_id != plugin_id:
            raise PluginStateError(
                f'Repository {repository_id!r} returned release for '
                f'{release.plugin_id!r}, expected {plugin_id!r}.'
            )
        artifact = await binding.fetcher.fetch(release)
        artifact = replace(
            artifact,
            source=f'{repository_id}:{release.artifact_uri}',
            expected_sha256=release.sha256,
        )
        return await self.install(artifact, enable=enable)

    async def enable(self, plugin_id: str) -> PluginOperationResult:
        async with self._operation_lock:
            self._ensure_initialized()
            self._require_record(plugin_id)
            records = self._records.copy()
            records[plugin_id] = replace(
                records[plugin_id],
                enabled=True,
                pending_restart=True,
                pending_removal=False,
            )
            records = self._enable_dependency_closure(
                plugin_id,
                records,
                self._candidates,
            )
            order, failures = self._activation_plan(records, self._candidates)
            if plugin_id not in order:
                failure = failures.get(plugin_id)
                raise PluginDependencyError(
                    failure.message if failure is not None else 'Plugin cannot be enabled.'
                )
            await self._dependency_manager.reconcile(
                self._requirements_for_order(order, self._candidates),
                activate=False,
            )
            self._records = records
            self._state_store.save(records)
            self._refresh_inventory()
            snapshot = self._snapshots[plugin_id]
            result = PluginOperationResult(plugin_id, snapshot.restart_required, snapshot)
        await self._publish()
        return result

    async def disable(
        self,
        plugin_id: str,
        *,
        cascade: bool = False,
    ) -> PluginOperationResult:
        async with self._operation_lock:
            self._ensure_initialized()
            self._require_record(plugin_id)
            affected = self._dependent_closure(plugin_id, enabled_only=True)
            direct_dependents = affected - {plugin_id}
            if direct_dependents and not cascade:
                raise PluginDependencyError(
                    f'Plugin {plugin_id!r} is required by enabled plugins: '
                    f'{", ".join(sorted(direct_dependents))}.'
                )

            records = self._records.copy()
            for affected_id in affected if cascade else {plugin_id}:
                records[affected_id] = replace(
                    records[affected_id],
                    enabled=False,
                    pending_restart=True,
                )
            order, _ = self._activation_plan(records, self._candidates)
            await self._dependency_manager.reconcile(
                self._requirements_for_order(order, self._candidates),
                activate=False,
            )
            self._records = records
            self._state_store.save(records)
            self._refresh_inventory()
            snapshot = self._snapshots[plugin_id]
            result = PluginOperationResult(plugin_id, snapshot.restart_required, snapshot)
        await self._publish()
        return result

    async def uninstall(
        self,
        plugin_id: str,
        *,
        cascade: bool = False,
    ) -> PluginOperationResult:
        async with self._operation_lock:
            self._ensure_initialized()
            self._require_record(plugin_id)
            affected = self._dependent_closure(plugin_id, enabled_only=False)
            dependents = affected - {plugin_id}
            if dependents and not cascade:
                raise PluginDependencyError(
                    f'Plugin {plugin_id!r} is required by enabled plugins: '
                    f'{", ".join(sorted(dependents))}.'
                )

            records = self._records.copy()
            for affected_id in affected if cascade else {plugin_id}:
                records[affected_id] = replace(
                    records[affected_id],
                    enabled=False,
                    pending_restart=True,
                    pending_removal=True,
                )
            order, _ = self._activation_plan(records, self._candidates)
            await self._dependency_manager.reconcile(
                self._requirements_for_order(order, self._candidates),
                activate=False,
            )
            self._records = records
            self._state_store.save(records)
            self._refresh_inventory()
            snapshot = self._snapshots[plugin_id]
            result = PluginOperationResult(plugin_id, True, snapshot)
        await self._publish()
        return result

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._refresh_inventory()

    def _refresh_inventory(self) -> None:
        records = self._state_store.load()
        candidates: dict[str, DiscoveredPlugin] = {}
        failures: dict[str, PluginFailure] = {}
        changed = False

        report = self._discovery.discover()
        self._discovery_failures = report.failures
        for candidate in report.plugins:
            plugin_id = candidate.manifest.plugin_id
            if plugin_id in records:
                continue
            records[plugin_id] = PluginRecord(
                plugin_id=plugin_id,
                plugin_version=candidate.manifest.plugin_version,
                path=candidate.path,
                enabled=True,
                pending_restart=self._started,
            )
            candidates[plugin_id] = candidate
            changed = True

        for plugin_id, record in tuple(records.items()):
            resolved_path = record.path.resolve()
            if resolved_path != record.path:
                record = replace(record, path=resolved_path)
                records[plugin_id] = record
                changed = True
            try:
                candidate = candidates.get(plugin_id) or self._discovery.discover_path(record.path)
                if candidate.manifest.plugin_id != plugin_id:
                    raise PluginStateError(
                        f'Plugin state id {plugin_id!r} does not match manifest id '
                        f'{candidate.manifest.plugin_id!r}.'
                    )
                if candidate.manifest.plugin_version != record.plugin_version:
                    raise PluginStateError(
                        f'Plugin {plugin_id!r} state expects version {record.plugin_version}, '
                        f'but manifest declares {candidate.manifest.plugin_version}.'
                    )
                self._validate_app_version(candidate)
                candidates[plugin_id] = candidate
            except Exception as exc:
                failures[plugin_id] = PluginFailure.from_exception(
                    PluginFailureStage.DISCOVERY,
                    exc,
                )

        self._records = records
        self._candidates = candidates
        snapshots: dict[str, PluginSnapshot] = {}
        for plugin_id, record in records.items():
            old_snapshot = self._snapshots.get(plugin_id)
            active_plugin = self._loaded_plugins.get(plugin_id)
            active_version: Version | None
            if plugin_id in self._active_plugins and active_plugin is not None:
                runtime_state = PluginRuntimeState.ACTIVE
                active_version = active_plugin.manifest.plugin_version
            elif (
                old_snapshot is not None
                and old_snapshot.runtime_state is PluginRuntimeState.FAILED
            ):
                runtime_state = PluginRuntimeState.FAILED
                active_version = old_snapshot.active_version
            elif not record.enabled or record.pending_removal:
                runtime_state = PluginRuntimeState.DISABLED
                active_version = None
            else:
                runtime_state = PluginRuntimeState.NOT_LOADED
                active_version = None

            failure = failures.get(plugin_id)
            if failure is not None:
                runtime_state = PluginRuntimeState.FAILED
            snapshot_candidate = candidates.get(plugin_id)
            snapshots[plugin_id] = PluginSnapshot(
                record=record,
                manifest=(snapshot_candidate.manifest if snapshot_candidate is not None else None),
                runtime_state=runtime_state,
                failure=failure,
                active_version=active_version,
            )

        self._snapshots = snapshots
        self._initialized = True
        if changed:
            self._state_store.save(records)

    async def _finalize_pending_removals(self) -> None:
        changed = False
        for plugin_id, record in tuple(self._records.items()):
            if not record.pending_removal:
                continue
            try:
                await self._artifact_installer.remove(record.path)
            except Exception as exc:
                self._snapshots[plugin_id] = replace(
                    self._snapshots[plugin_id],
                    runtime_state=PluginRuntimeState.FAILED,
                    failure=PluginFailure.from_exception(
                        PluginFailureStage.INSTALLATION,
                        exc,
                    ),
                )
                continue
            self._records.pop(plugin_id, None)
            self._candidates.pop(plugin_id, None)
            self._snapshots.pop(plugin_id, None)
            changed = True
        if changed:
            self._state_store.save(self._records)

    def _validate_app_version(self, plugin: DiscoveredPlugin) -> None:
        if self._app_version not in plugin.manifest.app_version:
            raise PluginError(
                f'Plugin {plugin.manifest.plugin_id!r} requires app version '
                f'{plugin.manifest.app_version}, current version is {self._app_version}.'
            )

    def _activation_plan(
        self,
        records: Mapping[str, PluginRecord],
        candidates: Mapping[str, DiscoveredPlugin],
    ) -> tuple[tuple[str, ...], dict[str, PluginFailure]]:
        eligible = {
            plugin_id
            for plugin_id, record in records.items()
            if record.enabled and not record.pending_removal and plugin_id in candidates
        }
        failures: dict[str, PluginFailure] = {}

        for plugin_id, record in records.items():
            if not record.enabled or record.pending_removal:
                continue
            candidate = candidates.get(plugin_id)
            if candidate is None:
                failures[plugin_id] = PluginFailure(
                    PluginFailureStage.VALIDATION,
                    f'Installed plugin {plugin_id!r} cannot be discovered.',
                )
                continue
            if self._app_version not in candidate.manifest.app_version:
                eligible.discard(plugin_id)
                failures[plugin_id] = PluginFailure(
                    PluginFailureStage.VALIDATION,
                    f'Plugin requires app version {candidate.manifest.app_version}.',
                )

        changed = True
        while changed:
            changed = False
            for plugin_id in tuple(eligible):
                manifest = candidates[plugin_id].manifest
                for dependency in manifest.plugin_dependencies:
                    dependency_record = records.get(dependency.plugin_id)
                    dependency_candidate = candidates.get(dependency.plugin_id)
                    if (
                        dependency_record is None
                        or not dependency_record.enabled
                        or dependency_record.pending_removal
                        or dependency.plugin_id not in eligible
                        or dependency_candidate is None
                    ):
                        eligible.remove(plugin_id)
                        failures[plugin_id] = PluginFailure(
                            PluginFailureStage.VALIDATION,
                            f'Required plugin {dependency.plugin_id!r} is not enabled.',
                        )
                        changed = True
                        break
                    if dependency_candidate.manifest.plugin_version not in dependency.version:
                        eligible.remove(plugin_id)
                        failures[plugin_id] = PluginFailure(
                            PluginFailureStage.VALIDATION,
                            f'Plugin {dependency.plugin_id!r} version '
                            f'{dependency_candidate.manifest.plugin_version} does not satisfy '
                            f'{dependency.version}.',
                        )
                        changed = True
                        break

        indegree = dict.fromkeys(eligible, 0)
        dependents: dict[str, set[str]] = {plugin_id: set() for plugin_id in eligible}
        for plugin_id in eligible:
            for dependency in candidates[plugin_id].manifest.plugin_dependencies:
                if dependency.plugin_id in eligible:
                    indegree[plugin_id] += 1
                    dependents[dependency.plugin_id].add(plugin_id)

        queue = sorted(plugin_id for plugin_id, value in indegree.items() if value == 0)
        order: list[str] = []
        while queue:
            plugin_id = queue.pop(0)
            order.append(plugin_id)
            for dependent in sorted(dependents[plugin_id]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
                    queue.sort()

        unresolved = eligible - set(order)
        for plugin_id in unresolved:
            failures[plugin_id] = PluginFailure(
                PluginFailureStage.VALIDATION,
                'Plugin is part of, or depends on, a dependency cycle.',
            )
        return tuple(order), failures

    def _enable_dependency_closure(
        self,
        plugin_id: str,
        records: dict[str, PluginRecord],
        candidates: Mapping[str, DiscoveredPlugin],
    ) -> dict[str, PluginRecord]:
        pending = [plugin_id]
        visited: set[str] = set()
        while pending:
            current_id = pending.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            current = candidates.get(current_id)
            if current is None:
                raise PluginDependencyError(f'Plugin {current_id!r} cannot be discovered.')
            for dependency in current.manifest.plugin_dependencies:
                dependency_record = records.get(dependency.plugin_id)
                dependency_candidate = candidates.get(dependency.plugin_id)
                if dependency_record is None or dependency_candidate is None:
                    raise PluginDependencyError(
                        f'Plugin {current_id!r} requires missing plugin {dependency.plugin_id!r}.'
                    )
                if dependency_record.pending_removal:
                    raise PluginDependencyError(
                        f'Plugin {dependency.plugin_id!r} is pending removal.'
                    )
                if dependency_candidate.manifest.plugin_version not in dependency.version:
                    raise PluginDependencyError(
                        f'Plugin {current_id!r} requires {dependency.plugin_id!r} '
                        f'{dependency.version}, installed version is '
                        f'{dependency_candidate.manifest.plugin_version}.'
                    )
                records[dependency.plugin_id] = replace(
                    dependency_record,
                    enabled=True,
                    pending_restart=(
                        dependency_record.pending_restart or not dependency_record.enabled
                    ),
                )
                pending.append(dependency.plugin_id)
        return records

    def _installed_dependency_failures(
        self,
        records: Mapping[str, PluginRecord],
        candidates: Mapping[str, DiscoveredPlugin],
    ) -> dict[str, PluginFailure]:
        installed_records = {
            plugin_id: replace(record, enabled=True)
            for plugin_id, record in records.items()
            if not record.pending_removal
        }
        _, failures = self._activation_plan(installed_records, candidates)
        return failures

    def _dependent_closure(self, plugin_id: str, *, enabled_only: bool) -> set[str]:
        affected = {plugin_id}
        changed = True
        while changed:
            changed = False
            for candidate_id, candidate in self._candidates.items():
                record = self._records.get(candidate_id)
                if (
                    candidate_id in affected
                    or record is None
                    or record.pending_removal
                    or (enabled_only and not record.enabled)
                ):
                    continue
                if any(
                    dependency.plugin_id in affected
                    for dependency in candidate.manifest.plugin_dependencies
                ):
                    affected.add(candidate_id)
                    changed = True
        return affected

    @staticmethod
    def _requirements_for_order(
        order: Sequence[str],
        candidates: Mapping[str, DiscoveredPlugin],
    ) -> tuple[Requirement, ...]:
        requirements: dict[str, Requirement] = {}
        for plugin_id in order:
            for requirement in candidates[plugin_id].manifest.python_dependencies:
                requirements[str(requirement)] = requirement
        return tuple(sorted(requirements.values(), key=str))

    def _apply_failures(self, failures: Mapping[str, PluginFailure]) -> None:
        for plugin_id, failure in failures.items():
            if plugin_id in self._snapshots:
                self._set_runtime_state(
                    plugin_id,
                    PluginRuntimeState.FAILED,
                    failure=failure,
                )

    def _set_runtime_state(
        self,
        plugin_id: str,
        runtime_state: PluginRuntimeState,
        *,
        failure: PluginFailure | None = None,
    ) -> None:
        snapshot = self._snapshots[plugin_id]
        active_version = snapshot.active_version
        loaded = self._loaded_plugins.get(plugin_id)
        if runtime_state is PluginRuntimeState.ACTIVE and loaded is not None:
            active_version = loaded.manifest.plugin_version
        self._snapshots[plugin_id] = replace(
            snapshot,
            runtime_state=runtime_state,
            failure=failure,
            active_version=active_version,
        )

    def _clear_pending_restart(self) -> None:
        changed = False
        for plugin_id, record in tuple(self._records.items()):
            if not record.pending_restart:
                continue
            updated = replace(record, pending_restart=False)
            self._records[plugin_id] = updated
            if plugin_id in self._snapshots:
                self._snapshots[plugin_id] = replace(
                    self._snapshots[plugin_id],
                    record=updated,
                )
            changed = True
        if changed:
            self._state_store.save(self._records)

    def _require_record(self, plugin_id: str) -> PluginRecord:
        try:
            return self._records[plugin_id]
        except KeyError as exc:
            raise PluginStateError(f'Plugin {plugin_id!r} is not installed.') from exc

    async def _publish(self) -> None:
        snapshot = self.snapshots
        for listener in tuple(self._listeners):
            try:
                result = listener(snapshot)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                continue
