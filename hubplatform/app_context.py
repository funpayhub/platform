from __future__ import annotations


__all__ = [
    'AppContext',
    'setup_default_app_context',
]

from typing import Any, Self
from collections.abc import Callable, Iterator, MutableMapping

from pyconfigtree import Properties

from hubplatform.telegram.callback_data.hash import HashService
from hubplatform.telegram.ui import UIRegistry


class AppContext(MutableMapping[str, Any]):
    def __init__(self) -> None:
        super().__init__()
        self._locked = False

        self._data: dict[str, Any] = {}
        self.check_items: dict[str, Callable[[Any], Any] | None] = {}

    def lock(self) -> None:
        self._locked = True

    def check_ready(self) -> None:
        for key, check_func in self.check_items.items():
            if key not in self._data:
                raise RuntimeError(f'Workflow data not ready: missing key {key!r}')

            if check_func is None:
                continue

            try:
                check_func(self._data[key])
            except ValueError as e:
                raise RuntimeError(
                    f'Workflow data not ready: {key!r} didnt pass the check.',
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f'Workflow data not ready: an error occurred while checking {key!r}.',
                ) from e

    def __delitem__(self, item: Any) -> None:
        with self:
            del self._data[item]

    def __getitem__(self, item: Any) -> Any:
        return self._data[item]

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __setitem__(self, key: str, value: Any) -> None:
        with self:
            self._data[key] = value

    def __enter__(self) -> Self:
        if self._locked:
            raise RuntimeError('App context is locked.')
        return self

    def __exit__(self, *_: Any) -> None:
        return

    def __getattribute__(self, item: str) -> Any:
        if item in ['pop', 'popitem', 'clear', 'update']:
            with self:
                return getattr(self._data, item)
        return super().__getattribute__(item)

    def __getattr__(self, item: str) -> Any:
        return self._data[item]


def setup_default_app_context(app_context: AppContext | None) -> AppContext:
    app_context = app_context if app_context is not None else AppContext()

    app_context.check_items.update(
        {
            'app_context': lambda i: i is app_context,
            'hash_service': lambda i: isinstance(i, HashService),  # todo: add is_ready check
            'tg_ui_registry': lambda i: isinstance(i, UIRegistry),
            'properties': lambda i: isinstance(i, Properties),
            'props': lambda i: i is app_context['properties'],
        }
    )
    return app_context
