from __future__ import annotations


__all__ = ['Package']

from dataclasses import dataclass

from packaging.version import Version


@dataclass(frozen=True)
class Package:
    name: str
    version: Version

    def __str__(self) -> str:
        return f'{self.name}=={self.version}'
