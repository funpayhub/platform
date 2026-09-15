from __future__ import annotations


__all__ = [
    'VersionManagerError',
    'VersionNotFoundError',
    'VersionDownloadError',
]

from packaging.version import Version

from hubplatform.i18n import I18nString
from hubplatform.exceptions import HubPlatformError


class VersionManagerError(HubPlatformError):
    pass


class VersionNotFoundError(VersionManagerError):
    def __init__(self, version: Version, msg: str | None = None) -> None:
        self.version = version
        super().__init__(
            msg
            if msg is not None
            else I18nString(
                key='hubplatform-version-not_found_error',
                fallback=f'Version {self.version} not found.',
                kwargs={'version': str(self.version)},
            )
        )


class VersionDownloadError(VersionManagerError):
    def __init__(self, version: Version, msg: str | None = None) -> None:
        self.version = version
        super().__init__(
            msg
            if msg is not None
            else I18nString(
                key='hubplatform-version-download_error',
                fallback=f'An unexpected error occurred while downloading version {self.version}.',
                kwargs={'version': str(self.version)},
            )
        )
