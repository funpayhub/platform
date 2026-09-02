from __future__ import annotations

from typing import Any
from collections.abc import Callable, Iterable, Awaitable


STEP = Callable[[object], Awaitable[Any]]


class PluginSetupRunner:
    def __init__(self) -> None:
        self._steps: dict[str, STEP] = {}
        self._steps_order: list[str] = []

    def add_step(self, step_name: str, step: STEP) -> None:
        if step_name in self._steps:
            raise ValueError(f'Step {step_name} already registered.')
        self._steps[step_name] = step
        self._steps_order.append(step_name)

    def set_order(self, steps_order: list[str]) -> None:
        self._steps_order = steps_order.copy()

    async def setup_plugins(self, plugins: Iterable[object]) -> None:
        for step_name in self._steps_order:
            if step_name not in self._steps:
                continue

            for plugin in plugins:
                await self._steps[step_name](plugin)
