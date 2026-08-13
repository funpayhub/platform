from __future__ import annotations


__all__ = [
    'VersionError',
    'VersionReservedError',
    'NotAValidVersionError',
    'VersionAlreadyExistsError',
    'VersionDoesNotExistError',
    'CompressionCodec',
    'CompressionCodecsRegistry',
]


import zlib
import base64
from typing import Final
from dataclasses import dataclass
from abc import ABCMeta, abstractmethod


class VersionError(ValueError): ...


class VersionReservedError(VersionError): ...


class NotAValidVersionError(VersionError): ...


class VersionAlreadyExistsError(VersionError): ...


class VersionDoesNotExistError(VersionError): ...


@dataclass(frozen=True, kw_only=True)
class CompressionCodec(metaclass=ABCMeta):
    version: str

    @abstractmethod
    def compress(self, data: str | bytes) -> bytes:
        pass

    @abstractmethod
    def decompress(self, data: str) -> str:
        pass


@dataclass(frozen=True, kw_only=True)
class ZLibBase85CompressionCodec(CompressionCodec):
    compression_dict: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.compression_dict, bytes):
            raise TypeError('Compression dict must be bytes.')

        if len(self.compression_dict) > 32768:
            raise ValueError(
                f'Compression dict is too large ({len(self.compression_dict)} > 32768).'
            )

    def compress(self, data: str | bytes) -> bytes:
        compressor = zlib.compressobj(level=9, wbits=-15, zdict=self.compression_dict)
        data = data.encode('utf-8') if isinstance(data, str) else data
        result = compressor.compress(data) + compressor.flush()
        return base64.b85encode(result)

    def decompress(self, data: str) -> str:
        if not data:
            return ''

        decoded = base64.b85decode(data)
        decompress_obj = zlib.decompressobj(wbits=-15, zdict=self.compression_dict)
        return (decompress_obj.decompress(decoded) + decompress_obj.flush()).decode('utf-8')


class CompressionCodecsRegistry:
    def __init__(
        self,
        reserved_codec: CompressionCodec,
    ) -> None:
        self._versions: Final[frozenset[str]] = frozenset('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

        if reserved_codec.version not in self._versions:
            raise ValueError('`reserved_version` must be on of A-Z0-9.')

        self._reserved_codec: Final[CompressionCodec] = reserved_codec
        self._default_codec_version = reserved_codec.version
        self._locked = False
        self._codecs: dict[str, CompressionCodec] = {reserved_codec.version: reserved_codec}

    @property
    def versions(self) -> frozenset[str]:
        return self._versions

    @property
    def reserved_version(self) -> CompressionCodec:
        return self._reserved_codec

    @property
    def default_codec_version(self) -> str:
        return self._default_codec_version

    @property
    def locked(self) -> bool:
        return self._locked

    def check_registry_locked(self) -> None:
        if self._locked:
            raise RuntimeError('Compression configuration locked.')

    def lock(self) -> None:
        self._locked = True

    def check_version(
        self,
        version: str,
        check_reserved: bool = False,
        ensure_exists: bool = False,
        ensure_not_exists: bool = False,
    ) -> None:
        if check_reserved and version == self._reserved_codec.version:
            raise VersionReservedError(f'Version {version!r} is reserved.')
        if version not in self._versions:
            raise NotAValidVersionError('Not a valid version.')
        if ensure_exists and version not in self._codecs:
            raise VersionDoesNotExistError(f'Version {version!r} does not exist.')
        if ensure_not_exists and version in self._codecs:
            raise VersionAlreadyExistsError(f'Version {version!r} already exists.')

    def add_codec(
        self, cfg: CompressionCodec, ensure_not_exists: bool = True, set_default: bool = False
    ) -> None:
        self.check_registry_locked()
        self.check_version(cfg.version, check_reserved=True, ensure_not_exists=ensure_not_exists)
        self._codecs[cfg.version] = cfg
        if set_default:
            self.set_default_codec_version(cfg.version)

    def get_codec(self, version: str, fallback_reserved: bool = False) -> CompressionCodec:
        try:
            self.check_version(version, ensure_exists=True)
        except VersionDoesNotExistError:
            if fallback_reserved:
                return self._reserved_codec
            raise
        return self._codecs[version]

    def set_default_codec_version(self, version: str) -> None:
        self.check_registry_locked()
        self.check_version(version, ensure_exists=True)
        self._default_codec_version = version

    def compress(
        self, data: str | bytes, version: str | None = None, fallback_reserved: bool = False
    ) -> bytes:
        if version is not None:
            try:
                self.check_version(version, ensure_exists=True)
            except VersionDoesNotExistError:
                if not fallback_reserved:
                    raise
                version = self._reserved_codec.version
        else:
            version = self._default_codec_version

        cfg = self.get_codec(version, fallback_reserved=False)
        return cfg.version.encode('utf-8') + cfg.compress(data)

    def decompress(self, data: str | bytes) -> str:
        data = data.decode('utf-8') if isinstance(data, bytes) else data
        if not data:
            return data
        version, payload = data[0], data[1:]
        if version not in self._versions:
            return data

        cfg = self.get_codec(version)
        return cfg.decompress(payload)
