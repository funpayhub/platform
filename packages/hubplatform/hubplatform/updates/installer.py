from __future__ import annotations


__all__ = ['InstallStage', 'ReleaseInstaller']

import os
import sys
import shutil
import asyncio
import hashlib
import zipfile
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath
from collections.abc import Callable, Awaitable

from packaging.version import Version, InvalidVersion

from hubplatform.updates import exceptions as exc
from hubplatform.logging.loggers import updates as updates_loggers

from .types import AppVersionInfo
from .manager import VersionsManager
from .releases import Releases, ReleaseManifest, replace_with_retry


logger = updates_loggers.installer

_UV_SYNC_TIMEOUT = 30 * 60
_CHECK_TIMEOUT = 5 * 60


class InstallStage(StrEnum):
    DOWNLOADING = auto()
    VERIFYING = auto()
    EXTRACTING = auto()
    INSTALLING_DEPENDENCIES = auto()
    CHECKING = auto()


type StageCallback = Callable[[InstallStage], Awaitable[None]]


class ReleaseInstaller:
    def __init__(
        self,
        versions_manager: VersionsManager,
        releases: Releases,
        launcher_protocol: int,
        uv_bin: str | Path | None = None,
    ) -> None:
        self._versions_manager = versions_manager
        self._releases = releases
        self._launcher_protocol = launcher_protocol
        self._uv_bin = Path(uv_bin) if uv_bin is not None else None
        self._lock = asyncio.Lock()

    @property
    def releases(self) -> Releases:
        return self._releases

    @property
    def is_installing(self) -> bool:
        return self._lock.locked()

    @property
    def versions_manager(self) -> VersionsManager:
        return self._versions_manager

    async def install(
        self,
        version: Version | str | AppVersionInfo,
        on_stage: StageCallback | None = None,
    ) -> Path:
        async with self._lock:
            info = (
                version
                if isinstance(version, AppVersionInfo)
                else await self.versions_manager.get_version_info(version)
            )
            target = self.releases.release_dir(info.version)
            if self.releases.is_installed(info.version):
                return target

            try:
                await asyncio.to_thread(self.releases.remove_leftovers)
                await self._install(info, target, on_stage)
            except exc.VersionManagerError:
                raise
            except Exception as e:
                logger.error('Unable to install release %s.', info.version, exc_info=True)
                raise exc.VersionInstallError(info.version) from e
            return target

    async def _install(
        self,
        info: AppVersionInfo,
        target: Path,
        on_stage: StageCallback | None,
    ) -> None:
        async def stage(value: InstallStage) -> None:
            logger.info('Installing release %s: %s.', info.version, value)
            if on_stage is not None:
                try:
                    await on_stage(value)
                except Exception:
                    logger.error('Install stage callback failed.', exc_info=True)

        await stage(InstallStage.DOWNLOADING)
        archive = await self._versions_manager.download_version(
            info,
            self._releases.downloads_dir,
            filename=f'{info.version}.zip',
            wait=True,
        )

        try:
            await stage(InstallStage.VERIFYING)
            await asyncio.to_thread(_verify_archive, archive, info.sha256)

            await stage(InstallStage.EXTRACTING)
            temp = self.releases.temp_dir(info.version)
            try:
                await asyncio.to_thread(_extract_archive, archive, temp)
                manifest = ReleaseManifest.read(temp)
                self._check_manifest(manifest, info.version)
                if target.exists():
                    await asyncio.to_thread(shutil.rmtree, target)
                await asyncio.to_thread(replace_with_retry, temp, target)
            finally:
                await asyncio.to_thread(shutil.rmtree, temp, True)
        finally:
            archive.unlink(missing_ok=True)

        await stage(InstallStage.INSTALLING_DEPENDENCIES)
        await self._run(
            [str(self._find_uv()), 'sync', '--no-dev', *self._uv_lock_args(target)],
            cwd=target,
            env={'UV_PROJECT_ENVIRONMENT': str(self._releases.venv_dir(info.version))},
            timeout=_UV_SYNC_TIMEOUT,
        )

        await stage(InstallStage.CHECKING)
        python = _venv_python(self._releases.venv_dir(info.version))
        await self._run(
            [str(python), '-m', 'compileall', '-q', '-x', r'[\\/]\.venv[\\/]', str(target)],
            cwd=target,
            timeout=_CHECK_TIMEOUT,
        )

        self._releases.mark_installed(info.version, info.sha256)
        logger.info('Release %s installed into %s.', info.version, target)

    def _check_manifest(self, manifest: ReleaseManifest, version: Version) -> None:
        if manifest.version != version:
            raise ValueError(
                f'Release archive contains version {manifest.version}, expected {version}.'
            )
        if manifest.launcher_protocol > self._launcher_protocol:
            raise exc.LauncherOutdatedError(
                version, manifest.launcher_protocol, self._launcher_protocol
            )

    @staticmethod
    def _uv_lock_args(release_dir: Path) -> list[str]:
        # Releases are expected to ship uv.lock; without it dependencies are resolved now.
        if (release_dir / 'uv.lock').is_file():
            return ['--frozen']
        logger.warning('Release %s has no uv.lock, resolving dependencies.', release_dir.name)
        return []

    def _find_uv(self) -> Path:
        if self._uv_bin is not None:
            return self._uv_bin
        if env_bin := os.environ.get('HUBPLATFORM_UV_BIN'):
            return Path(env_bin)
        try:
            from uv import find_uv_bin  # type: ignore[import-not-found,unused-ignore]
        except ImportError:
            pass
        else:
            return Path(find_uv_bin())
        if path_bin := shutil.which('uv'):
            return Path(path_bin)
        raise FileNotFoundError('Unable to find uv executable.')

    @staticmethod
    async def _run(
        args: list[str],
        cwd: Path,
        timeout: float,
        env: dict[str, str] | None = None,
    ) -> None:
        process_env = os.environ | (env or {})
        # The running release's venv must not leak into commands for the new release.
        process_env.pop('VIRTUAL_ENV', None)
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            env=process_env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

        text = output.decode(errors='replace').strip()
        if process.returncode != 0:
            raise RuntimeError(
                f'Command {args[0]!r} {" ".join(args[1:2])} exited with code '
                f'{process.returncode}:\n{text[-4000:]}'
            )
        if text:
            logger.debug('%s output:\n%s', Path(args[0]).name, text)


def _venv_python(venv: Path) -> Path:
    if sys.platform == 'win32':
        return venv / 'Scripts' / 'python.exe'
    return venv / 'bin' / 'python'


def _verify_archive(path: Path, sha256: str | None) -> None:
    if sha256 is None:
        logger.warning('No SHA-256 for %s, only checking archive integrity.', path.name)
    else:
        with path.open('rb') as f:
            actual = hashlib.file_digest(f, 'sha256').hexdigest()
        if actual != sha256.lower():
            raise ValueError(f'Archive SHA-256 mismatch: expected {sha256}, got {actual}.')

    with zipfile.ZipFile(path) as archive:
        if (bad := archive.testzip()) is not None:
            raise ValueError(f'Archive is corrupted: {bad}.')


def _extract_archive(path: Path, destination: Path) -> None:
    """Extract ``path`` into ``destination``.

    If all entries are inside one top-level directory (as in GitHub source archives),
    its contents are extracted instead.
    """
    with zipfile.ZipFile(path) as archive:
        members = [i for i in archive.infolist() if not i.is_dir()]
        if not members:
            raise ValueError('Archive is empty.')

        parts = [PurePosixPath(i.filename).parts for i in members]
        if len({p[0] for p in parts}) == 1 and all(len(p) > 1 for p in parts):
            parts = [p[1:] for p in parts]

        root = destination.resolve()
        targets = [root.joinpath(*p).resolve() for p in parts]
        for member, target in zip(members, targets, strict=True):
            if not target.is_relative_to(root):
                raise ValueError(f'Archive contains unsafe path: {member.filename}.')

        destination.mkdir(parents=True)
        for member, target in zip(members, targets, strict=True):
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
