from __future__ import annotations


__all__ = ['HubPlatformAppComponent', 'ComponentExtension']

from abc import ABC, abstractmethod

from hubplatform.app.context import AppContext


class HubPlatformAppComponent(ABC):
    async def run(self) -> None:
        pass

    def stop(self) -> None:
        pass

    async def wait_stop(self) -> None:
        pass

    async def setup_context(self, context: AppContext) -> None:
        pass

    async def install_extension(self, extension: ComponentExtension) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def component_name(self) -> str:
        pass


class ComponentExtension:
    pass
