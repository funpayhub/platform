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

from hubplatform.runtime import LauncherEnvironment, launcher_environment
from hubplatform.updates import exceptions as exc
from hubplatform.logging.loggers import updates as updates_loggers

from .types import AppVersionInfo
from .manager import VersionsManager
from .releases import Releases, ReleaseManifest, replace_with_retry


logger = updates_loggers.installer

_UV_SYNC_TIMEOUT = 30 * 60
_CHECK_TIMEOUT = 5 * 60
_HASH_CHUNK_SIZE = 1024 * 1024


class InstallStage(StrEnum):
    DOWNLOADING = auto()
    VERIFYING = auto()
    EXTRACTING = auto()
    INSTALLING_DEPENDENCIES = auto()
    CHECKING = auto()


type StageCallback = Callable[[InstallStage], Awaitable[None]]


class ReleaseInstaller:
    """Installs releases into the releases directory while the current release keeps running.

    Installing a release:

    1. downloads its archive into ``releases/.downloads``;
    2. verifies the archive (SHA-256 if the source provides it, zip CRC);
    3. unpacks it into a temporary directory and checks its manifest;
    4. renames the directory to ``releases/<version>`` (a venv can not be moved after creation);
    5. creates ``releases/<version>/.venv`` with ``uv sync``;
    6. byte-compiles the release with the new interpreter;
    7. writes the ``.installed`` marker.

    Nothing of it affects the running release. To switch to an installed release,
    :meth:`stage` it and stop the app with ``ExitCodes.UPDATE``.
    """

    def __init__(
        self,
        versions_manager: VersionsManager,
        releases: Releases,
        launcher_protocol: int,
        uv_bin: str | Path | None = None,
    ) -> None:
        """:param launcher_protocol: protocol of the launcher that will start installed releases.
        :param uv_bin: ``uv`` executable. By default: ``$HUBPLATFORM_UV_BIN``,
            the ``uv`` Python package, ``uv`` from ``PATH``.
        """
        self._versions_manager = versions_manager
        self._releases = releases
        self._launcher_protocol = launcher_protocol
        self._uv_bin = Path(uv_bin) if uv_bin is not None else None
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
        return cls(versions_manager, Releases(env.releases_dir), env.protocol)

    @property
    def releases(self) -> Releases:
        return self._releases

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
        :raises VersionInstallError: installation failed.
        :raises VersionManagerError: getting version info or downloading failed.
        """
        async with self._lock:
            info = (
                version
                if isinstance(version, AppVersionInfo)
                else await self._versions_manager.get_version_info(version)
            )
            target = self._releases.release_dir(info.version)
            if self._releases.is_installed(info.version):
                return target

            try:
                await asyncio.to_thread(self._remove_leftovers)
                await self._install(info, target, on_stage)
            except exc.VersionManagerError:
                raise
            except Exception as e:
                logger.error('Unable to install release %s.', info.version, exc_info=True)
                raise exc.VersionInstallError(info.version) from e
            return target

    def stage(self, version: Version | str) -> None:
        """Make installed ``version`` the release the launcher switches to on
        ``ExitCodes.UPDATE``.

        :raises ValueError: ``version`` is not installed.
        """
        self._releases.stage(Version(str(version)))

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
            temp = self._releases.temp_dir(info.version)
            try:
                await asyncio.to_thread(_extract_archive, archive, temp)
                manifest = ReleaseManifest.read(temp)
                self._check_manifest(manifest, info.version)
                if target.exists():
                    # Not installed (checked above): a leftover of an interrupted installation.
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

    def _remove_leftovers(self) -> None:
        """Remove temporary dirs and release dirs without ``.installed`` marker."""
        if not self._releases.path.is_dir():
            return
        for i in self._releases.path.iterdir():
            if i.is_symlink() or i.is_junction() or not i.is_dir():
                continue
            leftover = i.name.startswith(Releases.TEMP_PREFIX) or (
                _is_version_name(i.name) and not (i / Releases.MARKER_FILE).exists()
            )
            if leftover:
                logger.info('Removing leftover %s.', i)
                shutil.rmtree(i, ignore_errors=True)

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


def _is_version_name(name: str) -> bool:
    try:
        return str(Version(name)) == name
    except InvalidVersion:
        return False


def _venv_python(venv: Path) -> Path:
    if sys.platform == 'win32':
        return venv / 'Scripts' / 'python.exe'
    return venv / 'bin' / 'python'


def _verify_archive(path: Path, sha256: str | None) -> None:
    if sha256 is not None:
        digest = hashlib.sha256()
        with path.open('rb') as f:
            while chunk := f.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
        if digest.hexdigest() != sha256.lower():
            raise ValueError(
                f'Archive SHA-256 mismatch: expected {sha256}, got {digest.hexdigest()}.'
            )
    else:
        logger.warning('No SHA-256 for %s, only checking archive integrity.', path.name)

    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
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

        paths = [PurePosixPath(i.filename) for i in members]
        for i in paths:
            if i.is_absolute() or '..' in i.parts or ':' in i.parts[0]:
                raise ValueError(f'Archive contains unsafe path: {i}.')

        tops = {i.parts[0] for i in paths}
        strip = len(tops) == 1 and all(len(i.parts) > 1 for i in paths)

        destination.mkdir(parents=True)
        for member, member_path in zip(members, paths, strict=True):
            relative = PurePosixPath(*member_path.parts[1:]) if strip else member_path
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open('wb') as dst:
                shutil.copyfileobj(src, dst)
