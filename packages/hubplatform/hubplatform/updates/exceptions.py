from __future__ import annotations


__all__ = [
    'VersionManagerError',
    'VersionNotFoundError',
    'VersionDownloadError',
    'VersionDownloadInProgressError',
    'VersionInstallError',
    'LauncherOutdatedError',
]

from typing import TYPE_CHECKING

from packaging.version import Version

from hubplatform.i18n import I18nString
from hubplatform.exceptions import HubPlatformError


if TYPE_CHECKING:
    from pathlib import Path


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


class VersionDownloadInProgressError(VersionManagerError):
    def __init__(self, path: Path, msg: str | None = None) -> None:
        self.path = path
        super().__init__(
            msg
            if msg is not None
            else I18nString(
                key='hubplatform-version-download_in_progress_error',
                fallback='File {path} is already being downloaded.',
                kwargs={'path': str(self.path)},
            )
        )


class VersionInstallError(VersionManagerError):
    def __init__(self, version: Version, msg: str | None = None) -> None:
        self.version = version
        super().__init__(
            msg
            if msg is not None
            else I18nString(
                key='hubplatform-version-install_error',
                fallback=f'An unexpected error occurred while installing version {self.version}.',
                kwargs={'version': str(self.version)},
            )
        )


class LauncherOutdatedError(VersionInstallError):
    """The release requires a newer launcher protocol than the installed launcher implements."""

    def __init__(
        self,
        version: Version,
        required_protocol: int,
        launcher_protocol: int,
        msg: str | None = None,
    ) -> None:
        self.required_protocol = required_protocol
        self.launcher_protocol = launcher_protocol
        super().__init__(
            version,
            msg
            if msg is not None
            else I18nString(
                key='hubplatform-version-launcher_outdated_error',
                fallback=f'Version {version} requires a newer launcher '
                f'(protocol {required_protocol}, installed {launcher_protocol}). '
                f'Update the launcher manually.',
                kwargs={
                    'version': str(version),
                    'required_protocol': required_protocol,
                    'launcher_protocol': launcher_protocol,
                },
            ),
        )
