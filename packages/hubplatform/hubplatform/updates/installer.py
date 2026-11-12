from __future__ import annotations


__all__ = ['InstallStage', 'ReleaseInstaller']

import os
import shutil
import asyncio
import hashlib
import tarfile
import zipfile
from enum import StrEnum, auto
from pathlib import Path, PurePosixPath
from collections.abc import Callable, Awaitable

from packaging.version import Version

from hubplatform.runtime import LauncherEnvironment, launcher_environment
from hubplatform.updates import exceptions as exc
from hubplatform.logging.loggers import updates as updates_loggers

from .types import AppVersionInfo
from .manager import VersionsManager
from .manifest import Asset, ReleaseInfo, RuntimeInfo, UpdateManifest, current_platform
from .releases import Installation, runtime_python, replace_with_retry


logger = updates_loggers.installer

_CHECK_TIMEOUT = 60
_HASH_CHUNK_SIZE = 1024 * 1024


class InstallStage(StrEnum):
    FETCHING_MANIFEST = auto()
    DOWNLOADING_RUNTIME = auto()
    INSTALLING_RUNTIME = auto()
    DOWNLOADING_APP = auto()
    INSTALLING_APP = auto()


type StageCallback = Callable[[InstallStage], Awaitable[None]]


class ReleaseInstaller:
    """Installs releases while the current release keeps running.

    A release is described by its update manifest (:class:`UpdateManifest`) and consists of:

    * a runtime: Python + third-party packages, shared by releases with the same runtime id,
      one archive per platform (installed into ``runtimes/<id>`` if not installed yet);
    * the app: our code + first-party packages (installed into ``releases/<version>``).

    Both are downloaded, verified by SHA-256 and size, unpacked into a temporary directory
    and renamed into place; the ``.installed`` marker is written last. Nothing is compiled or
    resolved on this machine.

    Installing does not affect the running release. To switch to an installed release,
    :meth:`stage` it and stop the app with ``ExitCodes.UPDATE``.
    """

    def __init__(
        self,
        versions_manager: VersionsManager,
        installation: Installation,
        launcher_protocol: int,
        platform: str | None = None,
    ) -> None:
        """:param launcher_protocol: protocol of the launcher that will start installed releases.
        :param platform: python-build-standalone platform name, detected by default.
        """
        self._versions_manager = versions_manager
        self._installation = installation
        self._launcher_protocol = launcher_protocol
        self._platform = platform if platform is not None else current_platform()
        self._lock = asyncio.Lock()

    @classmethod
    def from_launcher(
        cls,
        versions_manager: VersionsManager,
        env: LauncherEnvironment | None = None,
    ) -> ReleaseInstaller | None:
        """Installer for the launcher that started the app, ``None`` if started directly."""
        env = env if env is not None else launcher_environment()
        if env is None:
            return None
        installation = Installation(env.releases_dir, env.runtimes_dir, env.envs_dir)
        return cls(versions_manager, installation, env.protocol)

    @property
    def installation(self) -> Installation:
        return self._installation

    @property
    def is_installing(self) -> bool:
        return self._lock.locked()

    async def install(
        self,
        version: Version | str | AppVersionInfo,
        on_stage: StageCallback | None = None,
    ) -> Path:
        """Download and install ``version``. Does nothing if it is already installed.

        Only one installation runs at a time, others wait for it.

        :param on_stage: called before each stage.
        :return: release directory.
        :raises VersionInstallError: installation failed (incl. subclasses: no manifest,
            unsupported platform, outdated launcher).
        :raises VersionManagerError: getting version info, the manifest or a file failed.
        """
        async with self._lock:
            info = (
                version
                if isinstance(version, AppVersionInfo)
                else await self._versions_manager.get_version_info(version)
            )
            if self._installation.is_release_installed(info.version):
                return self._installation.release_dir(info.version)

            try:
                return await self._install(info, on_stage)
            except exc.VersionManagerError:
                raise
            except Exception as e:
                logger.error('Unable to install release %s.', info.version, exc_info=True)
                raise exc.VersionInstallError(info.version) from e

    def stage(self, version: Version | str) -> None:
        """Make installed ``version`` the release the launcher switches to on
        ``ExitCodes.UPDATE``.

        :raises ValueError: ``version`` is not installed.
        """
        self._installation.stage(Version(str(version)))

    async def _install(self, info: AppVersionInfo, on_stage: StageCallback | None) -> Path:
        async def stage(value: InstallStage) -> None:
            logger.info('Installing release %s: %s.', info.version, value)
            if on_stage is not None:
                try:
                    await on_stage(value)
                except Exception:
                    logger.error('Install stage callback failed.', exc_info=True)

        await stage(InstallStage.FETCHING_MANIFEST)
        manifest = await self._versions_manager.get_manifest(info)
        self._check_manifest(manifest)
        runtime_asset = manifest.runtime.assets.get(self._platform or '')
        if runtime_asset is None:
            raise exc.UnsupportedPlatformError(manifest.version, self._platform)

        await asyncio.to_thread(self._remove_leftovers)

        runtime_id = manifest.runtime.id
        if not self._installation.is_runtime_installed(runtime_id):
            await stage(InstallStage.DOWNLOADING_RUNTIME)
            archive = await self._download(runtime_asset, f'runtime-{runtime_id}.tar.gz')
            await stage(InstallStage.INSTALLING_RUNTIME)
            try:
                await self._install_runtime(archive, runtime_asset, runtime_id)
            finally:
                archive.unlink(missing_ok=True)

        await stage(InstallStage.DOWNLOADING_APP)
        archive = await self._download(manifest.app, f'app-{manifest.version}.zip')
        await stage(InstallStage.INSTALLING_APP)
        try:
            target = await asyncio.to_thread(self._install_app, archive, manifest)
        finally:
            archive.unlink(missing_ok=True)

        logger.info('Release %s installed into %s.', manifest.version, target)
        return target

    def _check_manifest(self, manifest: UpdateManifest) -> None:
        if manifest.launcher_protocol > self._launcher_protocol:
            raise exc.LauncherOutdatedError(
                manifest.version, manifest.launcher_protocol, self._launcher_protocol
            )

    async def _download(self, asset: Asset, filename: str) -> Path:
        path = await self._versions_manager.download(
            asset.url,
            self._installation.downloads_dir,
            filename,
            wait=True,
        )
        try:
            await asyncio.to_thread(_verify, path, asset)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    async def _install_runtime(self, archive: Path, asset: Asset, runtime_id: str) -> None:
        runtimes_dir = self._installation.runtimes_dir
        temp = self._installation.temp_dir(runtimes_dir, runtime_id)
        try:
            await asyncio.to_thread(_extract_tar, archive, temp)
            runtime = RuntimeInfo.read(temp)
            if runtime.id != runtime_id:
                raise ValueError(f'Runtime archive contains {runtime.id}, expected {runtime_id}.')
            # The interpreter must start before the runtime is considered installed.
            await _run([str(runtime_python(temp)), '-s', '-c', 'import sys'], cwd=temp)

            target = self._installation.runtime_dir(runtime_id)
            await asyncio.to_thread(_remove, target)
            await asyncio.to_thread(replace_with_retry, temp, target)
            self._installation.mark_installed(target, asset.sha256)
        finally:
            await asyncio.to_thread(_remove, temp)

    def _install_app(self, archive: Path, manifest: UpdateManifest) -> Path:
        releases_dir = self._installation.releases_dir
        temp = self._installation.temp_dir(releases_dir, str(manifest.version))
        try:
            _extract_zip(archive, temp)
            release = ReleaseInfo.read(temp)
            if release.version != manifest.version:
                raise ValueError(
                    f'App archive contains version {release.version}, expected {manifest.version}.'
                )
            if release.runtime != manifest.runtime.id:
                raise ValueError(
                    f'App archive needs runtime {release.runtime}, '
                    f'manifest provides {manifest.runtime.id}.'
                )

            target = self._installation.release_dir(manifest.version)
            _remove(target)
            replace_with_retry(temp, target)
            self._installation.mark_installed(target, manifest.app.sha256)
            return target
        finally:
            _remove(temp)

    def _remove_leftovers(self) -> None:
        """Remove temporary directories and directories without ``.installed`` marker.

        Only names this installer creates are touched: ``.tmp-*``, versions in ``releases/``
        and runtime ids in ``runtimes/``.
        """
        for parent, is_ours in (
            (self._installation.releases_dir, _is_version_name),
            (self._installation.runtimes_dir, lambda name: not name.startswith('.')),
        ):
            if not parent.is_dir():
                continue
            for i in parent.iterdir():
                if i.is_symlink() or i.is_junction() or not i.is_dir():
                    continue
                leftover = i.name.startswith(Installation.TEMP_PREFIX) or (
                    is_ours(i.name) and not (i / Installation.MARKER_FILE).exists()
                )
                if leftover:
                    logger.info('Removing leftover %s.', i)
                    shutil.rmtree(i, ignore_errors=True)


async def _run(args: list[str], cwd: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONHOME', 'PYTHONPATH')}
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), _CHECK_TIMEOUT)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    if process.returncode != 0:
        raise RuntimeError(
            f'{Path(args[0]).name} exited with code {process.returncode}:\n'
            f'{output.decode(errors="replace")[-4000:]}'
        )


def _is_version_name(name: str) -> bool:
    try:
        return str(Version(name)) == name
    except ValueError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _verify(path: Path, asset: Asset) -> None:
    size = path.stat().st_size
    if size != asset.size:
        raise ValueError(f'{path.name}: size mismatch, expected {asset.size}, got {size}.')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    if digest.hexdigest() != asset.sha256:
        raise ValueError(f'{path.name}: SHA-256 mismatch.')


def _extract_tar(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    with tarfile.open(path, 'r:gz') as archive:
        # 'data' rejects absolute paths, '..', links outside the destination, device files.
        archive.extractall(destination, filter='data')


def _extract_zip(path: Path, destination: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            member = PurePosixPath(name)
            if member.is_absolute() or '..' in member.parts or ':' in name or '\\' in name:
                raise ValueError(f'Archive contains unsafe path: {name}.')
        destination.mkdir(parents=True)
        archive.extractall(destination)
