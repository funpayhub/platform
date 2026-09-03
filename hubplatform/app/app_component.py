__all__ = ['HubPlatformAppComponent']

from abc import ABC, abstractmethod


class HubPlatformAppComponent(ABC):
    @abstractmethod
    async def run(self) -> None: pass

    @abstractmethod
    async def stop(self) -> None: pass

    @abstractmethod
    async def wait_stop(self) -> None: pass
