from __future__ import annotations


__all__ = [
    'AppVersionInfo',
]

from dataclasses import dataclass

from packaging.version import Version


@dataclass(frozen=True)
class AppVersionInfo:
    version: Version
    notes: str
    manifest_url: str | None
    """URL of the update manifest (see :class:`hubplatform.updates.manifest.UpdateManifest`),
    ``None`` if the version can not be installed automatically."""
