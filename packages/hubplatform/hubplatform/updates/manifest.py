"""Release metadata files.

* ``manifest.json``: published with every release, read by the installer
  (:class:`UpdateManifest`);
* ``release.json``: inside an installed release, read by the launcher (:class:`ReleaseInfo`);
* ``runtime.json``: inside an installed runtime (:class:`RuntimeInfo`).

All of them are produced by the release build (``tools/build_release.py`` of the app).
"""

from __future__ import annotations


__all__ = [
    'MANIFEST_SCHEMA',
    'Asset',
    'RuntimeSpec',
    'UpdateManifest',
    'ReleaseInfo',
    'RuntimeInfo',
    'current_platform',
]

import re
import sys
import json
import platform
from typing import Any
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from collections.abc import Mapping

from packaging.version import Version, InvalidVersion


MANIFEST_SCHEMA = 1

_SHA256_RE = re.compile(r'[0-9a-f]{64}')
_RUNTIME_ID_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')


def current_platform() -> str | None:
    """python-build-standalone name of this machine's platform, ``None`` if unsupported."""
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}
    if machine not in arch:
        return None
    if sys.platform == 'win32':
        return f'{arch[machine]}-pc-windows-msvc'
    if sys.platform.startswith('linux') and platform.libc_ver()[0] == 'glibc':
        return f'{arch[machine]}-unknown-linux-gnu'
    return None


def _get(data: Mapping[str, Any], key: str, type_: type[Any]) -> Any:
    value = data.get(key)
    if not isinstance(value, type_) or isinstance(value, bool) and type_ is not bool:
        raise ValueError(f'{key!r} must be {type_.__name__}, got {value!r}.')
    return value


def _check_schema(data: Any) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError('Expected an object.')
    schema = _get(data, 'schema', int)
    if schema != MANIFEST_SCHEMA:
        raise ValueError(f'Unsupported schema {schema}.')
    return data


def _version(value: Any) -> Version:
    try:
        return Version(str(value))
    except InvalidVersion as e:
        raise ValueError(f'Invalid version {value!r}.') from e


def _runtime_id(value: Any) -> str:
    if not isinstance(value, str) or not _RUNTIME_ID_RE.fullmatch(value):
        raise ValueError(f'Invalid runtime id {value!r}.')
    return value


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'Invalid path {value!r}.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or ':' in value or '\\' in value:
        raise ValueError(f'Path must be relative: {value!r}.')
    return value


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    size: int

    @classmethod
    def from_json(cls, data: Any) -> Asset:
        if not isinstance(data, Mapping):
            raise ValueError('Asset must be an object.')
        url = _get(data, 'url', str)
        sha256 = _get(data, 'sha256', str).lower()
        size = _get(data, 'size', int)
        if not url.startswith(('https://', 'http://')):
            raise ValueError(f'Invalid asset URL {url!r}.')
        if not _SHA256_RE.fullmatch(sha256):
            raise ValueError(f'Invalid SHA-256 {sha256!r}.')
        if size <= 0:
            raise ValueError(f'Invalid asset size {size}.')
        return cls(url=url, sha256=sha256, size=size)


@dataclass(frozen=True)
class RuntimeSpec:
    id: str
    python: str
    assets: Mapping[str, Asset]
    """Runtime archive per platform (python-build-standalone platform names)."""

    @classmethod
    def from_json(cls, data: Any) -> RuntimeSpec:
        if not isinstance(data, Mapping):
            raise ValueError('Runtime must be an object.')
        assets = _get(data, 'assets', dict)
        return cls(
            id=_runtime_id(data.get('id')),
            python=_get(data, 'python', str),
            assets={str(k): Asset.from_json(v) for k, v in assets.items()},
        )


@dataclass(frozen=True)
class UpdateManifest:
    """``manifest.json``: everything needed to install a release."""

    version: Version
    launcher_protocol: int
    app: Asset
    runtime: RuntimeSpec

    @classmethod
    def from_json(cls, data: Any) -> UpdateManifest:
        """:raises ValueError: invalid manifest."""
        data = _check_schema(data)
        return cls(
            version=_version(data.get('version')),
            launcher_protocol=_get(data, 'launcher_protocol', int),
            app=Asset.from_json(data.get('app')),
            runtime=RuntimeSpec.from_json(data.get('runtime')),
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> UpdateManifest:
        try:
            return cls.from_json(json.loads(data))
        except json.JSONDecodeError as e:
            raise ValueError(f'Manifest is not valid JSON: {e}.') from e


@dataclass(frozen=True)
class ReleaseInfo:
    """``release.json`` of an installed release."""

    version: Version
    runtime: str
    entrypoint: str
    launcher_protocol: int
    pythonpath: tuple[str, ...]
    """Directories (relative to the release) added to ``sys.path``."""

    FILENAME = 'release.json'

    @classmethod
    def read(cls, release_dir: Path) -> ReleaseInfo:
        """:raises ValueError: missing or invalid."""
        try:
            data = _check_schema(
                json.loads((release_dir / cls.FILENAME).read_text(encoding='utf-8'))
            )
        except FileNotFoundError:
            raise ValueError(f'Release has no {cls.FILENAME}.') from None
        except json.JSONDecodeError as e:
            raise ValueError(f'{cls.FILENAME} is not valid JSON: {e}.') from e

        entrypoint = _relative_path(data.get('entrypoint'))
        if not (release_dir / entrypoint).is_file():
            raise ValueError(f'Release entrypoint {entrypoint!r} does not exist.')
        return cls(
            version=_version(data.get('version')),
            runtime=_runtime_id(data.get('runtime')),
            entrypoint=entrypoint,
            launcher_protocol=_get(data, 'launcher_protocol', int),
            pythonpath=tuple(_relative_path(i) for i in _get(data, 'pythonpath', list)),
        )


@dataclass(frozen=True)
class RuntimeInfo:
    """``runtime.json`` of an installed runtime."""

    id: str
    python: str
    platform: str

    FILENAME = 'runtime.json'

    @classmethod
    def read(cls, runtime_dir: Path) -> RuntimeInfo:
        """:raises ValueError: missing or invalid."""
        try:
            data = _check_schema(
                json.loads((runtime_dir / cls.FILENAME).read_text(encoding='utf-8'))
            )
        except FileNotFoundError:
            raise ValueError(f'Runtime has no {cls.FILENAME}.') from None
        except json.JSONDecodeError as e:
            raise ValueError(f'{cls.FILENAME} is not valid JSON: {e}.') from e
        return cls(
            id=_runtime_id(data.get('id')),
            python=_get(data, 'python', str),
            platform=_get(data, 'platform', str),
        )
