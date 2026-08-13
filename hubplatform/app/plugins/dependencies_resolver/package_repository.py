from abc import ABC, abstractmethod
from dataclasses import dataclass
import sys
from importlib.metadata import PackageNotFoundError

from packaging.version import Version
from importlib import metadata
import pkgutil


_PYTHON_VERSION = Version(
    f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
)


@dataclass(frozen=True)
class PackageMetaData:
    name: str
    version: Version
    dependencies: list[str]


class DistributionNotFoundError(Exception): ...


class DistributionRepository(ABC):
    @abstractmethod
    async def _get_versions(self, distribution_name: str) -> list[Version]: pass

    @abstractmethod
    async def _get_distribution_meta(self, distribution_name: str, version: Version) -> PackageMetaData: pass

    async def get_versions(self, distribution_name: str) -> list[Version]:
        self._check_distribution_name(distribution_name)
        return await self._get_versions(distribution_name)

    async def get_distribution_meta(self, distribution_name: str, version: Version) -> PackageMetaData:
        self._check_distribution_name(distribution_name)
        return await self._get_distribution_meta(distribution_name, version)

    def _check_distribution_name(self, distribution_name: str) -> None:
        if not isinstance(distribution_name, str):
            raise TypeError('Distribution name must be a string.')

        if not distribution_name:
            raise ValueError('Distribution name cannot be empty.')


class LocalDistributionRepository(DistributionRepository):
    async def _get_versions(self, distribution_name: str) -> list[Version]:
        try:
            return [Version(metadata.version(distribution_name))]
        except PackageNotFoundError:
            raise DistributionNotFoundError(f'Distribution {distribution_name!r} not found.')

    async def _get_distribution_meta(self, distribution_name: str, version: Version) -> PackageMetaData:
        try:
            result = metadata.metadata(distribution_name)
        except PackageNotFoundError:
            raise DistributionNotFoundError(f'Distribution {distribution_name!r} not found.')

        print(result)
        return PackageMetaData(
            name=distribution_name,
            version=Version(result['version']),
            dependencies=result['Requires-Dist'],
        )



async def main():
    repo = LocalDistributionRepository()
    versions = await repo.get_versions('aiogram')
    print(versions)
    print(await repo.get_distribution_meta('aiogram', versions[0]))


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())