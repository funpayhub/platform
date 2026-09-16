from __future__ import annotations


__all__ = ['PackageInstaller', 'PipPackageInstaller']


import os
import sys
import json
import shutil
import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from collections.abc import Sequence, Collection

from .types import DependencyPlan, DependencyEnvironment
from ..exceptions import DependencyInstallationError


class PackageInstaller(ABC):
    @abstractmethod
    async def install_packages(self, plan: DependencyPlan) -> DependencyEnvironment:
        pass

    async def collect_garbage(self, keep_fingerprints: Collection[str]) -> None:
        return


class PipPackageInstaller(PackageInstaller):
    """Builds immutable, content-addressed ``--target`` environments."""

    def __init__(
        self,
        environments_path: str | Path,
        python_executable: str | Path = Path(sys.executable),
        *,
        pip_args: Sequence[str] = (),
    ) -> None:
        self._environments_path = Path(environments_path).resolve()
        self._python_executable = Path(python_executable)
        self._pip_args = tuple(pip_args)

    @property
    def environments_path(self) -> Path:
        return self._environments_path

    @property
    def python_executable(self) -> Path:
        return self._python_executable

    async def install_packages(self, plan: DependencyPlan) -> DependencyEnvironment:
        target_path = self._environments_path / plan.fingerprint
        site_packages = target_path / 'site-packages'
        marker_path = target_path / 'environment.json'
        if marker_path.is_file() and site_packages.is_dir():
            return DependencyEnvironment(
                fingerprint=plan.fingerprint,
                site_packages=site_packages,
            )

        self._environments_path.mkdir(parents=True, exist_ok=True)
        staging_path = (
            self._environments_path / f'.staging-{plan.fingerprint[:12]}-{os.urandom(8).hex()}'
        )
        if staging_path.exists():
            shutil.rmtree(staging_path)
        staging_site_packages = staging_path / 'site-packages'
        staging_site_packages.mkdir(parents=True)

        try:
            if plan.packages:
                command = [
                    str(self._python_executable),
                    '-m',
                    'pip',
                    'install',
                    '--disable-pip-version-check',
                    '--no-input',
                    '--no-deps',
                    '--target',
                    str(staging_site_packages),
                    *self._pip_args,
                    *(str(package) for package in plan.packages),
                ]
                try:
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await process.communicate()
                except OSError as exc:
                    raise DependencyInstallationError(
                        f'Cannot execute pip using {str(self._python_executable)!r}.'
                    ) from exc

                if process.returncode != 0:
                    details = stderr.decode(errors='replace').strip()
                    raise DependencyInstallationError(
                        f'Cannot install plugin dependencies with pip: '
                        f'{details or "unknown error"}'
                    )

            marker = {
                'fingerprint': plan.fingerprint,
                'requirements': [str(value) for value in plan.requirements],
                'constraints': [str(value) for value in plan.constraints],
                'packages': [
                    {
                        'name': package.name,
                        'version': str(package.version),
                        'install_requirement': package.install_requirement,
                        'hashes': list(package.hashes),
                    }
                    for package in plan.packages
                ],
            }
            (staging_path / 'environment.json').write_text(
                json.dumps(marker, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8',
            )

            try:
                staging_path.replace(target_path)
            except FileExistsError:
                shutil.rmtree(staging_path, ignore_errors=True)
            return DependencyEnvironment(
                fingerprint=plan.fingerprint,
                site_packages=site_packages,
            )
        except Exception:
            shutil.rmtree(staging_path, ignore_errors=True)
            raise

    async def collect_garbage(self, keep_fingerprints: Collection[str]) -> None:
        keep = set(keep_fingerprints)
        await asyncio.to_thread(self._collect_garbage, keep)

    def _collect_garbage(self, keep: set[str]) -> None:
        if not self._environments_path.is_dir():
            return
        for path in tuple(self._environments_path.iterdir()):
            if not path.is_dir():
                continue
            if path.name.startswith('.staging-'):
                shutil.rmtree(path, ignore_errors=True)
                continue
            if path.name not in keep and (path / 'environment.json').is_file():
                shutil.rmtree(path)
