from __future__ import annotations


__all__ = ['DependencyResolver', 'PipDependencyResolver']

import sys
import json
import asyncio
from typing import Iterable
from abc import ABC, abstractmethod

from packaging.version import Version
from packaging.requirements import Requirement

from .types import Package


class DependencyResolver(ABC):
    async def resolve_dependencies(self, dependencies: Iterable[Requirement]) -> list[Package]:
        try:
            return await self._resolve_dependencies(dependencies)
        except Exception:
            raise
        # todo: custom exception

    @abstractmethod
    async def _resolve_dependencies(self, dependencies: Iterable[Requirement]) -> list[Package]:
        pass


class PipDependencyResolver(DependencyResolver):
    async def _resolve_dependencies(self, dependencies: Iterable[Requirement]) -> list[Package]:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            '-m',
            'pip',
            'install',
            '--dry-run',
            '--ignore-installed',
            '--quite',
            '--report',
            '-',
            *[str(i) for i in dependencies],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise Exception('Resolve error')  # todo: custom exception

        try:
            parsed = json.loads(stdout)
            parsed = parsed['install']
        except Exception as e:
            raise Exception('Resolve error') from e  # todo: custom exception

        result = []
        for i in parsed:
            metadata = i['metadata']
            result.append(Package(name=metadata['name'], version=Version(metadata['version'])))
        return result
