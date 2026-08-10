from __future__ import annotations


__all__ = [
    'State',
    'StateFromQuery',
    'StateFilter',
]


from typing import TYPE_CHECKING, Any, Self, Literal, overload
from dataclasses import dataclass

from aiogram.filters import StateFilter as AiogramStateFilter

from hubplatform.core import classproperty
from hubplatform.telegram.callback_data.models import ParsedEnvelope


if TYPE_CHECKING:
    from aiogram.types import Message, CallbackQuery
    from aiogram.fsm.context import FSMContext


class State:
    if TYPE_CHECKING:
        __identifier__: str
        identifier: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        identifier = kwargs.pop('identifier', None)

        if identifier is None:
            raise TypeError(
                f"'State {cls.__name__!r} must be defined with keyword argument 'identifier'."
            )

        if not isinstance(identifier, str) or not identifier:
            raise ValueError('State identifier must be an empty string.')

        cls.__identifier__ = identifier
        super().__init_subclass__(**kwargs)

    @classproperty
    def identifier(cls) -> str:
        return cls.__identifier__

    async def set(self, state: FSMContext) -> None:
        await state.set_state(self.identifier)
        await state.set_data({'_hubplatform_state_data': self})

    @classmethod
    async def get(cls, state: FSMContext) -> Self:
        state_id = await state.get_state()
        if state_id != cls.identifier:
            raise RuntimeError('State mismatch.')

        data = await state.get_data()
        if '_hubplatform_state_data' not in data or not isinstance(
            data['_hubplatform_state_data'], cls
        ):
            raise RuntimeError('State mismatch.')

        return data['_hubplatform_state_data']

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

        obj = (await state.get_data()).get('_hubplatform_state_data')
        if not isinstance(obj, cls):
            raise RuntimeError('State type mismatch.')

        await state.clear()
        return obj

    @classmethod
    def filter(cls) -> StateFilter:
        return StateFilter(cls)


@dataclass
class StateFromQuery(State, identifier='StateFromQuery'):
    query: CallbackQuery

    @property
    def message(self) -> Message:
        return self.query.message

    @property
    def callback_envelope(self) -> ParsedEnvelope:
        if hasattr(self.query, '__parsed__'):
            return getattr(self.query, '__parsed__')
        cb = ...
        setattr(cb, '__parsed__', cb)
        return cb

    @property
    def ui_history(self) -> list[MenuHistoryNode]:
        return self.callback_data.ui_history


class StateFilter(AiogramStateFilter):
    def __init__(self, state: State | type[State]) -> None:
        super().__init__(state.identifier)
