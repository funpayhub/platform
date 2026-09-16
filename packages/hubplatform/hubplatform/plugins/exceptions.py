from __future__ import annotations

from hubplatform.exceptions import HubPlatformError


class PluginError(HubPlatformError):
    pass


class PluginDiscoveryError(PluginError):
    pass


class PluginManifestError(PluginDiscoveryError):
    pass


class PluginLoadError(PluginError):
    pass


class PluginContractError(PluginLoadError):
    pass


class PluginActivationError(PluginError):
    pass


class PluginStateError(PluginError):
    pass


class PluginArtifactError(PluginError):
    pass


class PluginDependencyError(PluginError):
    pass


class DependencyResolutionError(PluginDependencyError):
    pass


class DependencyInstallationError(PluginDependencyError):
    pass
