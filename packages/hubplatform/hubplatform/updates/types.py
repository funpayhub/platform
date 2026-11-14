from __future__ import annotations


__all__ = [
    'AppVersionInfo',
]

from dataclasses import dataclass

from packaging.version import Version


@dataclass(frozen=True)
class AppVersionInfo:
    version: Version
    """Release version."""

    notes: str
    """Release notes."""

    url: str
    """URL of the release archive (zip)."""

    sha256: str | None = None
    """Expected SHA-256 of the archive (hex), ``None`` if the source does not provide it."""
