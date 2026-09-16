from __future__ import annotations


__all__ = [
    'InstalledPluginArtifact',
    'LocalPluginArtifactInstaller',
    'PluginArtifact',
    'PluginArtifactInstaller',
    'PreparedPluginArtifact',
]


import os
import stat
import shutil
import asyncio
import hashlib
import zipfile
from dataclasses import replace, dataclass
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
from collections.abc import Collection

from .types import DiscoveredPlugin
from .loader import PluginDiscovery
from .exceptions import PluginArtifactError


@dataclass(frozen=True)
class PluginArtifact:
    """A local plugin artifact acquired by an application or repository adapter."""

    path: Path
    source: str | None = None
    expected_sha256: str | None = None


@dataclass(frozen=True)
class PreparedPluginArtifact:
    artifact: PluginArtifact
    staging_path: Path
    plugin: DiscoveredPlugin
    sha256: str


@dataclass(frozen=True)
class InstalledPluginArtifact:
    plugin: DiscoveredPlugin
    source: str
    sha256: str


class PluginArtifactInstaller(ABC):
    @abstractmethod
    async def prepare(self, artifact: PluginArtifact) -> PreparedPluginArtifact:
        pass

    @abstractmethod
    async def commit(self, prepared: PreparedPluginArtifact) -> InstalledPluginArtifact:
        pass

    @abstractmethod
    async def discard(self, prepared: PreparedPluginArtifact) -> None:
        pass

    @abstractmethod
    async def remove(self, path: Path) -> None:
        pass

    async def collect_garbage(self, referenced_paths: Collection[Path]) -> None:
        return


class LocalPluginArtifactInstaller(PluginArtifactInstaller):
    """Stages directory/ZIP artifacts and commits them to immutable release paths."""

    def __init__(self, plugins_path: str | Path) -> None:
        self._plugins_path = Path(plugins_path).resolve()
        self._staging_path = self._plugins_path / '.staging'
        self._installed_path = self._plugins_path / '.installed'
        self._discovery = PluginDiscovery(self._plugins_path)

    @property
    def plugins_path(self) -> Path:
        return self._plugins_path

    async def prepare(self, artifact: PluginArtifact) -> PreparedPluginArtifact:
        try:
            return await asyncio.to_thread(self._prepare, artifact)
        except PluginArtifactError:
            raise
        except Exception as exc:
            raise PluginArtifactError(
                f'Cannot prepare plugin artifact {str(artifact.path)!r}.'
            ) from exc

    def _prepare(self, artifact: PluginArtifact) -> PreparedPluginArtifact:
        artifact_path = artifact.path.resolve()
        if not artifact_path.exists():
            raise PluginArtifactError(f'Plugin artifact {str(artifact_path)!r} does not exist.')

        self._staging_path.mkdir(parents=True, exist_ok=True)
        staging_path = self._staging_path / os.urandom(16).hex()
        staging_path.mkdir()
        payload_path = staging_path / 'payload'
        try:
            if artifact_path.is_dir():
                self._ensure_directory_has_no_symlinks(artifact_path)
                sha256 = self._hash_directory(artifact_path)
                shutil.copytree(artifact_path, payload_path)
            elif artifact_path.is_file() and artifact_path.suffix.lower() == '.zip':
                sha256 = self._hash_file(artifact_path)
                unpacked_path = staging_path / 'unpacked'
                unpacked_path.mkdir()
                with zipfile.ZipFile(artifact_path) as archive:
                    self._validate_zip(archive)
                    archive.extractall(unpacked_path)
                root = self._find_archive_root(unpacked_path)
                shutil.move(str(root), payload_path)
            else:
                raise PluginArtifactError('Plugin artifact must be a directory or a ZIP archive.')

            expected = artifact.expected_sha256
            if expected is not None and not self._hashes_equal(sha256, expected):
                raise PluginArtifactError(
                    f'Plugin artifact checksum mismatch: expected {expected}, got {sha256}.'
                )

            discovered = self._discovery.discover_path(payload_path)
            normalized_artifact = replace(artifact, path=artifact_path)
            return PreparedPluginArtifact(
                artifact=normalized_artifact,
                staging_path=staging_path,
                plugin=discovered,
                sha256=sha256,
            )
        except Exception:
            shutil.rmtree(staging_path, ignore_errors=True)
            raise

    async def commit(self, prepared: PreparedPluginArtifact) -> InstalledPluginArtifact:
        try:
            return await asyncio.to_thread(self._commit, prepared)
        except PluginArtifactError:
            raise
        except Exception as exc:
            raise PluginArtifactError(
                f'Cannot commit plugin {prepared.plugin.manifest.plugin_id!r}.'
            ) from exc

    def _commit(self, prepared: PreparedPluginArtifact) -> InstalledPluginArtifact:
        self._ensure_staging_path(prepared.staging_path)
        manifest = prepared.plugin.manifest
        release_name = f'{manifest.plugin_version}-{prepared.sha256[:12]}'
        target_path = self._installed_path / manifest.plugin_id / release_name
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            shutil.rmtree(prepared.staging_path, ignore_errors=True)
        else:
            os.replace(prepared.plugin.path, target_path)
            shutil.rmtree(prepared.staging_path, ignore_errors=True)

        plugin = self._discovery.discover_path(target_path)
        return InstalledPluginArtifact(
            plugin=plugin,
            source=prepared.artifact.source or str(prepared.artifact.path),
            sha256=prepared.sha256,
        )

    async def discard(self, prepared: PreparedPluginArtifact) -> None:
        await asyncio.to_thread(self._discard, prepared)

    def _discard(self, prepared: PreparedPluginArtifact) -> None:
        self._ensure_staging_path(prepared.staging_path)
        shutil.rmtree(prepared.staging_path, ignore_errors=True)

    async def remove(self, path: Path) -> None:
        await asyncio.to_thread(self._remove, path)

    def _remove(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._plugins_path) or resolved == self._plugins_path:
            raise PluginArtifactError(
                f'Refusing to remove plugin path outside {str(self._plugins_path)!r}.'
            )
        if not resolved.exists():
            return
        if not (resolved / 'manifest.json').is_file():
            raise PluginArtifactError(
                f'Refusing to remove {str(resolved)!r}: manifest.json is missing.'
            )
        shutil.rmtree(resolved, ignore_errors=False)

    async def collect_garbage(self, referenced_paths: Collection[Path]) -> None:
        referenced = {path.resolve() for path in referenced_paths}
        await asyncio.to_thread(self._collect_garbage, referenced)

    def _collect_garbage(self, referenced: set[Path]) -> None:
        if self._staging_path.is_dir():
            for staging_path in tuple(self._staging_path.iterdir()):
                if staging_path.is_dir():
                    shutil.rmtree(staging_path)
        if not self._installed_path.is_dir():
            return
        for plugin_path in tuple(self._installed_path.iterdir()):
            if not plugin_path.is_dir():
                continue
            for release_path in tuple(plugin_path.iterdir()):
                if not release_path.is_dir() or release_path.resolve() in referenced:
                    continue
                if (release_path / 'manifest.json').is_file():
                    shutil.rmtree(release_path)
            try:
                plugin_path.rmdir()
            except OSError:
                pass

    def _ensure_staging_path(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._staging_path) or resolved == self._staging_path:
            raise PluginArtifactError(f'Invalid staging path {str(path)!r}.')

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _hash_directory(cls, path: Path) -> str:
        digest = hashlib.sha256()
        for file_path in sorted(item for item in path.rglob('*') if item.is_file()):
            relative = file_path.relative_to(path).as_posix().encode()
            digest.update(len(relative).to_bytes(8, 'big'))
            digest.update(relative)
            with file_path.open('rb') as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b''):
                    digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _ensure_directory_has_no_symlinks(path: Path) -> None:
        for child in path.rglob('*'):
            if child.is_symlink():
                raise PluginArtifactError(
                    f'Plugin directory contains a symbolic link: {str(child)!r}.'
                )

    @staticmethod
    def _validate_zip(archive: zipfile.ZipFile) -> None:
        for member in archive.infolist():
            path = PurePosixPath(member.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts:
                raise PluginArtifactError(
                    f'ZIP member {member.filename!r} escapes the artifact directory.'
                )
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise PluginArtifactError(f'ZIP member {member.filename!r} is a symbolic link.')

    @staticmethod
    def _find_archive_root(unpacked_path: Path) -> Path:
        if (unpacked_path / 'manifest.json').is_file():
            return unpacked_path
        children = tuple(unpacked_path.iterdir())
        if len(children) == 1 and children[0].is_dir():
            root = children[0]
            if (root / 'manifest.json').is_file():
                return root
        raise PluginArtifactError(
            'ZIP must contain manifest.json at its root or in one top-level directory.'
        )

    @staticmethod
    def _hashes_equal(actual: str, expected: str) -> bool:
        expected = expected.lower()
        if expected.startswith('sha256:'):
            expected = expected.removeprefix('sha256:')
        return actual.lower() == expected
