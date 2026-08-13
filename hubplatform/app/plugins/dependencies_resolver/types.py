from dataclasses import dataclass

from packaging.specifiers import SpecifierSet
from packaging.version import Version


@dataclass(frozen=True)
class Package:
    name: str
    version: Version


@dataclass(frozen=True)
class Dependency:
    source: Package
    name: str
    requirement: SpecifierSet


ROOT = Package(name='__app__', version=Version('1.0'))


