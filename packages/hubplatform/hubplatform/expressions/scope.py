__all__ = ['ExpressionsScope']

from collections.abc import Generator


class ExpressionsScope:
    def __init__(self) -> None:
        self._bindings: dict[str, str] = {}
        self._subscopes: dict[str, ExpressionsScope] = {}

    def __setitem__(self, key: str, value: str | ExpressionsScope) -> None:
        if not isinstance(key, str):
            raise TypeError(f'Key must be an instance of str, not {type(key)}.')
        if isinstance(value, str):
            self.bind(key, value)
        elif isinstance(value, ExpressionsScope):
            self.add_subscope(key, value)

        raise TypeError(
            f'Value must be an instance of str to add a binding '
            f'or an instance of ExpressionsScope to add a subscope, '
            f'{type(value)} was given.'
        )

    def bind(self, key: str, expression_id: str) -> None:
        if key in self._bindings:
            raise KeyError(f'Binding {key!r} already exists.')  # todo: custom error

        self._bindings[key] = expression_id

    def unbind(self, key: str) -> None:
        self._bindings.pop(key, None)

    def add_subscope(self, subscope_id: str, subscope: ExpressionsScope) -> None:
        self._check_subscope(subscope_id, subscope)
        self._subscopes[subscope_id] = subscope

    def _check_subscope(self, subscope_id: str, subscope: ExpressionsScope) -> None:
        if not isinstance(subscope_id, str):
            raise TypeError(f'Subscope id must be an instance of str, not {type(subscope_id)}.')
        if not isinstance(subscope, ExpressionsScope):
            raise TypeError(
                f'Subscope must be an instance of ExpressionsScope, not {type(subscope)}.'
            )
        if subscope_id in self._subscopes:
            raise KeyError(f'Subscope {subscope_id!r} already exists.')  # todo: custom error

        for _, subsubscope in subscope.subscopes(recursive=True):
            if subsubscope is self:
                raise RuntimeError(f'Subscopes loop.')  # todo: custom error

        collision = set(self.bindings(recursive=True)) & set(subscope.bindings(recursive=True))
        if collision:
            raise RuntimeError(f'Names collision: {collision}.')  # todo: custom error

    def subscopes(
        self,
        recursive: bool = False
    ) -> Generator[tuple[tuple[str, ...], ExpressionsScope], None, None]:
        for subscope_id, subscope in self._subscopes.items():
            yield (subscope_id, ), subscope

            if recursive:
                for (path, subsubscope) in subscope.subscopes(recursive=True):
                    yield (subscope_id, *path), subsubscope

    def bindings(self, recursive: bool = True) -> dict[str, str]:
        if not recursive:
            return self._bindings.copy()

        bindings = self._bindings.copy()
        for subscope_path, subscope in self.subscopes(recursive=False):
            bindings.update(subscope.bindings(recursive=True))
        return bindings
