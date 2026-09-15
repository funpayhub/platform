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
    url: str
