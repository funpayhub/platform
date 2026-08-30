from __future__ import annotations


__all__ = [
    'State',
    # 'StateFromQuery',
    'StateFilter',
]

from typing import Any, Self, Final, Literal, overload

from aiogram.types import TelegramObject
from aiogram.filters import Filter, StateFilter as AiogramStateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.magic_filter import MagicFilter


class State:
    identifier: Final[str] = ''

    def __init_subclass__(cls, **kwargs: Any) -> None:

        if 'identifier' not in kwargs:
            raise TypeError(f"{cls.__name__} must be defined with keyword argument 'identifier'.")
        identifier = kwargs.pop('identifier', None)

        if not isinstance(identifier, str):
            raise ValueError(
                f"'identifier' must be a string, not {identifier.__class__.__name__}.'"
            )
        if not identifier:
            raise ValueError('Identifier cannot be empty.')

        cls.identifier = identifier  # type: ignore[misc]  # Final[str] is for public API.
        super().__init_subclass__(**kwargs)

    async def set(self, state: FSMContext) -> None:
        await state.set_state(self.identifier)
        await state.set_data({'data': self})

    @classmethod
    async def get(cls, state: FSMContext) -> Self:
        state_id = await state.get_state()
        if state_id != cls.identifier:
            raise RuntimeError('State mismatch.')

        data = await state.get_data()
        if data.get('data') is None or not isinstance(data['data'], cls):
            raise RuntimeError('State mismatch.')

        return data['data']

    @overload
    @classmethod
    async def clear(
        cls,
        state: FSMContext,
        check: Literal[False],
        raise_: bool = ...,
    ) -> None: ...

    @overload
    @classmethod
    async def clear(
        cls,
        state: FSMContext,
        check: Literal[True] = ...,
        raise_: Literal[True] = ...,
    ) -> Self: ...

    @overload
    @classmethod
    async def clear(
        cls,
        state: FSMContext,
        check: Literal[True] = ...,
        raise_: Literal[False] = ...,
    ) -> None: ...

    @classmethod
    async def clear(
        cls,
        state: FSMContext,
        check: bool = True,
        raise_: bool = True,
    ) -> Self | None:
        if not check:
            await state.clear()
            return None

        identifier = await state.get_state()
        if identifier != cls.identifier:
            if raise_:
                raise RuntimeError('State mismatch.')
            return None

        obj = (await state.get_data()).get('data')
        if not isinstance(obj, cls):
            raise RuntimeError('State type mismatch.')

        await state.clear()
        return obj

    @classmethod
    def filter(cls, rule: MagicFilter | None = None) -> StateFilter:
        return StateFilter(cls, rule=rule)


class StateFilter(Filter):
    def __init__(self, state: type[State], rule: MagicFilter | None = None) -> None:
        self._aiogram_filter = AiogramStateFilter(state.identifier)
        self._rule = rule
        self._state = state

    async def __call__(
        self,
        obj: TelegramObject,
        state: FSMContext,
        raw_state: str | None = None,
    ) -> bool | dict[str, Any]:
        result = await self._aiogram_filter(obj, raw_state)
        if result is False:
            return False

        data = await state.get_data()
        data_obj = data.get('data')
        if not isinstance(data_obj, self._state):
            return False

        if self._rule is None:
            return result

        if not self._rule.resolve(data_obj):
            return False
        return result
