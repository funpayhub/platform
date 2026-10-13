__all__ = ['ExpressionsScope']

from collections.abc import Generator, Sequence


class ExpressionsScope:
    def __init__(self) -> None:
        self._bindings: dict[str, str] = {}
        self._subscopes: dict[str, ExpressionsScope] = {}

    def bind(self, key: str, expression_id: str) -> None:
        if key in self._bindings:
            raise KeyError(f'Binding {key!r} already exists.')  # todo: custom error

        self._bindings[key] = expression_id

    def add_subscope(self, subscope_id: str, subscope: ExpressionsScope) -> None:
        if subscope_id in self._subscopes:
            raise KeyError(f'Subscope {subscope_id!r} already exists.')

        self._subscopes[subscope_id] = subscope

    def unbind(self, key: str) -> None:
        self._bindings.pop(key, None)

    def subscopes(
        self,
        recursive: bool = False
    ) -> Generator[tuple[tuple[str, ...], ExpressionsScope], None, None]:
        for subscope_id, subscope in self._subscopes.items():
            yield (subscope_id, ), subscope

            if recursive:
                for (path, subsubscope) in subscope.subscopes(recursive=True):
                    yield (subscope_id, *path), subsubscope