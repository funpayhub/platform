from __future__ import annotations


__all__ = ['PackageInstaller', 'PipPackageInstaller']

import sys
import asyncio
from typing import Sequence
from abc import ABC, abstractmethod

from .types import Package


class PackageInstaller(ABC):
    async def install_packages(self, packages: Sequence[Package]) -> None:
        try:
            return await self._install_packages(packages)
        except Exception:
            raise
        # todo: custom exception

    @abstractmethod
    async def _install_packages(self, packages: Sequence[Package]) -> None:
        pass


class PipPackageInstaller(PackageInstaller):
    async def _install_packages(self, packages: Sequence[Package]) -> None:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            '-m',
            'pip',
            'install',
            *[str(i) for i in packages],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await proc.communicate()

        if proc.returncode != 0:
            raise Exception('Install error')  # todo: custom exception
        return
