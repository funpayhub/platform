from __future__ import annotations


__all__ = ['DependencyResolver', 'PipDependencyResolver']


import sys
import json
import asyncio
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from collections.abc import Iterable, Sequence

from packaging.utils import canonicalize_name
from packaging.version import Version
from packaging.requirements import Requirement

from .types import Package, DependencyPlan
from ..exceptions import DependencyResolutionError


def normalize_requirements(
    requirements: Iterable[Requirement | str],
) -> tuple[Requirement, ...]:
    if isinstance(requirements, str):
        raise TypeError('Requirements must be an iterable, not a single string.')

    result: dict[str, Requirement] = {}
    for value in requirements:
        requirement = value if isinstance(value, Requirement) else Requirement(value)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        result[str(requirement)] = requirement
    return tuple(sorted(result.values(), key=str))


class DependencyResolver(ABC):
    @abstractmethod
    async def resolve_dependencies(
        self,
        dependencies: Iterable[Requirement | str],
        *,
        constraints: Iterable[Requirement | str] = (),
    ) -> DependencyPlan:
        pass


class PipDependencyResolver(DependencyResolver):
    """Uses pip's report mode to produce a deterministic installation plan."""

    def __init__(
        self,
        python_executable: str | Path = Path(sys.executable),
        *,
        pip_args: Sequence[str] = (),
    ) -> None:
        self._python_executable = Path(python_executable)
        self._pip_args = tuple(pip_args)

    @property
    def python_executable(self) -> Path:
        return self._python_executable

    async def resolve_dependencies(
        self,
        dependencies: Iterable[Requirement | str],
        *,
        constraints: Iterable[Requirement | str] = (),
    ) -> DependencyPlan:
        normalized = normalize_requirements(dependencies)
        normalized_constraints = normalize_requirements(constraints)
        if not normalized:
            return DependencyPlan.create((), normalized_constraints, ())

        constraint_path: Path | None = None
        command = [
            str(self._python_executable),
            '-m',
            'pip',
            'install',
            '--dry-run',
            '--ignore-installed',
            '--quiet',
            '--disable-pip-version-check',
            '--report',
            '-',
            *self._pip_args,
        ]
        try:
            if normalized_constraints:
                with tempfile.NamedTemporaryFile(
                    mode='w',
                    encoding='utf-8',
                    prefix='hubplatform-plugin-constraints-',
                    suffix='.txt',
                    delete=False,
                ) as file:
                    constraint_path = Path(file.name)
                    file.write('\n'.join(str(value) for value in normalized_constraints))
                    file.write('\n')
                command.extend(('--constraint', str(constraint_path)))
            command.extend(str(value) for value in normalized)

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except OSError as exc:
            raise DependencyResolutionError(
                f'Cannot execute pip using {str(self._python_executable)!r}.'
            ) from exc
        finally:
            if constraint_path is not None:
                constraint_path.unlink(missing_ok=True)

        if process.returncode != 0:
            details = stderr.decode(errors='replace').strip()
            raise DependencyResolutionError(
                f'Cannot resolve plugin dependencies with pip: {details or "unknown error"}'
            )

        try:
            report = json.loads(stdout)
            packages = self._parse_report(report)
        except DependencyResolutionError:
            raise
        except Exception as exc:
            raise DependencyResolutionError('Pip returned an invalid JSON report.') from exc

        return DependencyPlan.create(normalized, normalized_constraints, packages)

    @classmethod
    def _parse_report(cls, report: object) -> tuple[Package, ...]:
        if not isinstance(report, dict):
            raise DependencyResolutionError('Pip report root must be an object.')
        raw_install = report.get('install')
        if not isinstance(raw_install, list):
            raise DependencyResolutionError('Pip report has no installation list.')

        packages: dict[str, Package] = {}
        for raw_item in raw_install:
            package = cls._parse_package(raw_item)
            existing = packages.get(package.canonical_name)
            if existing is not None and existing.version != package.version:
                raise DependencyResolutionError(
                    f'Pip selected multiple versions of {package.name!r}.'
                )
            packages[package.canonical_name] = package
        return tuple(packages.values())

    @staticmethod
    def _parse_package(raw_item: object) -> Package:
        if not isinstance(raw_item, dict):
            raise DependencyResolutionError('Pip installation entry must be an object.')
        metadata = raw_item.get('metadata')
        if not isinstance(metadata, dict):
            raise DependencyResolutionError('Pip installation entry has no metadata.')
        name = metadata.get('name')
        version = metadata.get('version')
        if not isinstance(name, str) or not isinstance(version, str):
            raise DependencyResolutionError('Pip package name/version is invalid.')

        install_requirement = f'{canonicalize_name(name)}=={version}'
        if raw_item.get('is_direct') is True:
            download_info = raw_item.get('download_info')
            if not isinstance(download_info, dict):
                raise DependencyResolutionError('Direct package has no download information.')
            url = download_info.get('url')
            if not isinstance(url, str) or not url:
                raise DependencyResolutionError('Direct package URL is invalid.')
            install_requirement = url

        hashes: tuple[str, ...] = ()
        download_info = raw_item.get('download_info')
        if isinstance(download_info, dict):
            archive_info = download_info.get('archive_info')
            if isinstance(archive_info, dict):
                raw_hashes = archive_info.get('hashes')
                if isinstance(raw_hashes, dict):
                    hashes = tuple(
                        sorted(
                            f'{algorithm}:{digest}'
                            for algorithm, digest in raw_hashes.items()
                            if isinstance(algorithm, str) and isinstance(digest, str)
                        )
                    )

        return Package(
            name=name,
            version=Version(version),
            install_requirement=install_requirement,
            hashes=hashes,
        )
