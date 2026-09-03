from __future__ import annotations


__all__ = ['AppContext']

import inspect
from typing import Any, Self
from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Mapping, Callable, Iterator, Awaitable


@dataclass(frozen=True)
class _ProvidedValue:
    value: object
    provided_by: str


_CHECK = Callable[[object], Awaitable[bool] | bool]


@dataclass(frozen=True)
class _Requirement:
    required_by: str
    key: str
    check: _CHECK | None

    async def check_value(self, value: object) -> bool:
        if self.check is None:
            return True
        result = self.check(value)
        if inspect.isawaitable(result):
            result = await result
        return result


class AppContext(Mapping[str, Any]):
    def __init__(self) -> None:
        super().__init__()
        self._locked = False

        self._provided_values: dict[str, _ProvidedValue] = {}
        self._requirements: dict[str, dict[str, _Requirement]] = defaultdict(dict)

    def __enter__(self) -> Self:
        if self._locked:
            raise RuntimeError('App context is locked.')
        return self

    def __exit__(self, *_: Any) -> None:
        return

    def __getitem__(self, item: Any) -> Any:
        return self._provided_values[item].value

    def __len__(self) -> int:
        return len(self._provided_values)

    def __iter__(self) -> Iterator[str]:
        return iter(self._provided_values)

    def require(self, required_by: str, key: str, check: _CHECK | None = None) -> None:
        with self:
            if required_by in self._requirements.get(key, {}):
                raise RuntimeError(f'{required_by!r} already required a {key!r}.')

            self._requirements[key][required_by] = _Requirement(
                required_by=required_by, key=key, check=check
            )

    def provide(self, provided_by: str, key: str, value: object) -> None:
        with self:
            if key in self._provided_values:
                raise RuntimeError(
                    f'{key!r} is already provided by {self._provided_values[key].provided_by!r}.'
                )

            self._provided_values[key] = _ProvidedValue(provided_by=provided_by, value=value)

    async def lock(self) -> None:
        if self._locked:
            return

        await self.check()
        self._locked = True

    async def check(self) -> None:
        for key, request in self._requirements.items():
            if key not in self._provided_values:
                raise RuntimeError(
                    f'{key!r} is required by {", ".join(f"{i!r}" for i in request.keys())} but '
                    f'was not provided.'
                )

            provided_value = self._provided_values[key]
            for requested_by, requirement in request.items():
                try:
                    result = await requirement.check_value(provided_value.value)
                except Exception as e:
                    raise RuntimeError(
                        f'An error occurred while {requested_by!r} was checking {key!r}.'
                    ) from e

                if not result:
                    raise RuntimeError(
                        f"{requested_by!r} didn't accept value of {key!r} ({provided_value!r})."
                    )
