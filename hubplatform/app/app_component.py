from __future__ import annotations


__all__ = ['HubPlatformAppComponent']

from abc import ABC, abstractmethod

from hubplatform.app_context import AppContext


class HubPlatformAppComponent(ABC):
    async def run(self) -> None:
        pass

    def stop(self) -> None:
        pass

    async def wait_stop(self) -> None:
        pass

    async def setup_context(self, context: AppContext) -> None:
        pass

    @property
    @abstractmethod
    def component_name(self) -> str:
        pass
