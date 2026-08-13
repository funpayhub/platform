from __future__ import annotations


__all__ = [
    'VersionError',
    'VersionReservedError',
    'NotAValidVersionError',
    'VersionAlreadyExistsError',
    'VersionDoesNotExistError',
    'check_version',
    'CompressionConfig',
    'add_compression_config',
    'lock_compression_config',
    'get_compression_config',
    'set_default_compression_config_version',
    'compress',
    'decompress'
]


import zlib
import base64
from typing import Final
from dataclasses import dataclass


_VERSIONS: Final[frozenset[str]] = frozenset('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')
_RESERVED_COMPRESSION_CONFIG_VERSION: Final[str] = '0'
_DEFAULT_COMPRESSION_CONFIG_VERSION: str = _RESERVED_COMPRESSION_CONFIG_VERSION
_COMPRESSION_CFG_LOCKED: bool = False


class VersionError(ValueError): ...


class VersionReservedError(VersionError): ...


class NotAValidVersionError(VersionError): ...


class VersionAlreadyExistsError(VersionError): ...


class VersionDoesNotExistError(VersionError): ...


def check_version(
    version: str,
    check_reserved: bool = False,
    ensure_exists: bool = False,
    ensure_not_exists: bool = False,
) -> None:
    if check_reserved and version == _RESERVED_COMPRESSION_CONFIG_VERSION:
        raise VersionReservedError(f'Version {version!r} is reserved.')
    if version not in _VERSIONS:
        raise NotAValidVersionError(
            'Not a valid version. Valid version is a single character 1-9A-Z.'
        )
    if ensure_exists and version not in _COMPRESSION_CONFIGS:
        raise VersionDoesNotExistError(f'Version {version!r} does not exist.')
    if ensure_not_exists and version in _COMPRESSION_CONFIGS:
        raise VersionAlreadyExistsError(f'Version {version!r} already exists.')


@dataclass(frozen=True)
class CompressionConfig:
    version: str
    compression_dict: bytes

    def __post_init__(self) -> None:
        check_version(self.version, check_reserved=False)

        if not isinstance(self.compression_dict, bytes):
            raise TypeError('Compression dict must be a bytes.')

        if len(self.compression_dict) > 32768:
            raise ValueError(
                f'Compression dict is too large ({len(self.compression_dict)} > 32768).'
            )


_COMPRESSION_CONFIGS: dict[str, CompressionConfig] = {
    '0': CompressionConfig(version='0', compression_dict=b''),
}


def _check_config_locked() -> None:
    if _COMPRESSION_CFG_LOCKED:
        raise RuntimeError('Compression configuration locked.')


def add_compression_config(cfg: CompressionConfig, ensure_not_exists: bool = True) -> None:
    global _COMPRESSION_CONFIGS

    _check_config_locked()
    check_version(cfg.version, check_reserved=True, ensure_not_exists=ensure_not_exists)
    _COMPRESSION_CONFIGS[cfg.version] = cfg


def lock_compression_config() -> None:
    global _COMPRESSION_CFG_LOCKED
    _COMPRESSION_CFG_LOCKED = True


def get_compression_config(version: str, fallback_reserved: bool = False) -> CompressionConfig:
    try:
        check_version(version, ensure_exists=True)
    except VersionDoesNotExistError:
        if fallback_reserved:
            return _COMPRESSION_CONFIGS[_RESERVED_COMPRESSION_CONFIG_VERSION]
        raise
    return _COMPRESSION_CONFIGS[version]


def set_default_compression_config_version(version: str) -> None:
    global _DEFAULT_COMPRESSION_CONFIG_VERSION

    _check_config_locked()
    check_version(version, ensure_exists=True)
    _DEFAULT_COMPRESSION_CONFIG_VERSION = version


def compress(
    data: str | bytes, version: str | None = None, fallback_reserved: bool = True
) -> bytes:
    if version is not None:
        try:
            check_version(version, ensure_exists=True)
        except VersionDoesNotExistError:
            if not fallback_reserved:
                raise
            version = _RESERVED_COMPRESSION_CONFIG_VERSION
    else:
        version = _DEFAULT_COMPRESSION_CONFIG_VERSION

    compression_config = get_compression_config(version, fallback_reserved=False)

    compressor = zlib.compressobj(
        level=9,
        wbits=-15,
        zdict=compression_config.compression_dict,
    )
    data = data.encode('utf-8') if isinstance(data, str) else data
    result = compressor.compress(data) + compressor.flush()

    return compression_config.version.encode('utf-8') + base64.b85encode(result)


def decompress(data: str | bytes) -> str:
    data = data.decode('utf-8') if isinstance(data, bytes) else data
    if not data:
        return ''

    version, payload = data[0], data[1:]
    if version not in _VERSIONS:
        return data

    compression_config = get_compression_config(version)
    decoded = base64.b85decode(payload)

    decompress_obj = zlib.decompressobj(
            wbits=-15,
            zdict=compression_config.compression_dict,
        )

    return (decompress_obj.decompress(decoded) + decompress_obj.flush()).decode('utf-8')
