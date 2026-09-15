from __future__ import annotations

from .manifest import (
    LoadedPlugin as LoadedPlugin,
    PluginAuthor as PluginAuthor,
    PluginManifest as PluginManifest,
)
from .dependencies.manager import (
    DependencyManager as DependencyManager,
    global_dependency_manager as global_dependency_manager,
)
