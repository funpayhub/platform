from __future__ import annotations

from hubplatform.exceptions import HubPlatformError


class AppError(HubPlatformError):
    pass


class AppSetupError(AppError):
    """Base class for errors raised during app setup.

    This exception is raised directly only when an unexpected error occurs
    during app setup.
    """

    pass


class AppContextSetupError(AppSetupError):
    """Raised when an error occurs while setting up the app context."""

    pass


class ComponentExtensionInstallError(AppSetupError):
    """Raised when an error occurs while installing an app component extension."""

    pass
