from __future__ import annotations


__all__ = ['HubPlatformAppComponent', 'ComponentExtension']

from typing import TYPE_CHECKING
from abc import ABC, abstractmethod


if TYPE_CHECKING:
    from hubplatform.app import HubPlatformApp


class HubPlatformAppComponent(ABC):
    async def run(self) -> None:
        pass

    def stop(self) -> None:
        pass

    async def wait_stop(self) -> None:
        pass

    async def setup(self, app: HubPlatformApp) -> None:
        pass

    async def install_extension(self, extension: ComponentExtension) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def component_name(self) -> str:
        pass


class ComponentExtension:
    pass
