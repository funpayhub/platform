from __future__ import annotations


__all__ = [
    'DependencyEnvironment',
    'DependencyPlan',
    'Package',
]


import hashlib
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable

from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.requirements import Requirement


@dataclass(frozen=True)
class Package:
    name: str
    version: Version
    install_requirement: str
    hashes: tuple[str, ...] = ()

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    def __str__(self) -> str:
        return self.install_requirement


@dataclass(frozen=True)
class DependencyPlan:
    requirements: tuple[Requirement, ...]
    constraints: tuple[Requirement, ...]
    packages: tuple[Package, ...]
    fingerprint: str

    @classmethod
    def create(
        cls,
        requirements: Iterable[Requirement],
        constraints: Iterable[Requirement],
        packages: Iterable[Package],
    ) -> DependencyPlan:
        normalized_requirements = tuple(sorted(requirements, key=str))
        normalized_constraints = tuple(sorted(constraints, key=str))
        normalized_packages = tuple(
            sorted(packages, key=lambda package: (package.canonical_name, package.version))
        )
        digest = hashlib.sha256()
        for category, values in (
            ('requirement', normalized_requirements),
            ('constraint', normalized_constraints),
        ):
            for value in values:
                encoded = f'{category}\0{value}\n'.encode()
                digest.update(encoded)
        for package in normalized_packages:
            encoded = (
                f'package\0{package.canonical_name}\0{package.version}\0'
                f'{package.install_requirement}\0{",".join(package.hashes)}\n'
            ).encode()
            digest.update(encoded)
        return cls(
            requirements=normalized_requirements,
            constraints=normalized_constraints,
            packages=normalized_packages,
            fingerprint=digest.hexdigest(),
        )


@dataclass(frozen=True)
class DependencyEnvironment:
    fingerprint: str
    site_packages: Path
