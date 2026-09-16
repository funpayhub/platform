from __future__ import annotations


__all__ = [
    'DiscoveredPlugin',
    'LoadedPlugin',
    'PluginFailure',
    'PluginFailureStage',
    'PluginOperationResult',
    'PluginRecord',
    'PluginRuntimeState',
    'PluginSnapshot',
]


from typing import Generic, TypeVar
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from packaging.version import Version

from .manifest import PluginManifest


PluginT = TypeVar('PluginT')


class PluginRuntimeState(StrEnum):
    DISABLED = 'disabled'
    NOT_LOADED = 'not_loaded'
    LOADED = 'loaded'
    ACTIVE = 'active'
    FAILED = 'failed'


class PluginFailureStage(StrEnum):
    DISCOVERY = 'discovery'
    VALIDATION = 'validation'
    DEPENDENCIES = 'dependencies'
    LOADING = 'loading'
    ACTIVATION = 'activation'
    INSTALLATION = 'installation'
    STATE = 'state'


@dataclass(frozen=True)
class PluginFailure:
    stage: PluginFailureStage
    message: str
    exception_type: str | None = None

    @classmethod
    def from_exception(
        cls,
        stage: PluginFailureStage,
        exception: BaseException,
    ) -> PluginFailure:
        return cls(
            stage=stage,
            message=str(exception),
            exception_type=type(exception).__name__,
        )


@dataclass(frozen=True)
class DiscoveredPlugin:
    path: Path
    manifest: PluginManifest


@dataclass(frozen=True)
class LoadedPlugin(Generic[PluginT]):
    discovered: DiscoveredPlugin
    instance: PluginT
    module_name: str

    @property
    def path(self) -> Path:
        return self.discovered.path

    @property
    def manifest(self) -> PluginManifest:
        return self.discovered.manifest


@dataclass(frozen=True)
class PluginRecord:
    """Persistent desired state of one installed plugin."""

    plugin_id: str
    plugin_version: Version
    path: Path
    enabled: bool = True
    pending_restart: bool = False
    pending_removal: bool = False
    source: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class PluginSnapshot:
    """Immutable application-facing view of persistent and runtime state."""

    record: PluginRecord
    manifest: PluginManifest | None
    runtime_state: PluginRuntimeState
    failure: PluginFailure | None = None
    active_version: Version | None = None

    @property
    def plugin_id(self) -> str:
        return self.record.plugin_id

    @property
    def enabled(self) -> bool:
        return self.record.enabled

    @property
    def restart_required(self) -> bool:
        return self.record.pending_restart


@dataclass(frozen=True)
class PluginOperationResult:
    plugin_id: str
    restart_required: bool
    snapshot: PluginSnapshot | None
