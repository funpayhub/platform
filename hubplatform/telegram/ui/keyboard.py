from __future__ import annotations


__all__ = [
    'Keyboard',
    'KeyboardSpecBuilder',
    'KeyboardModificationCallable',
    'KeyboardBlockSpec',
    'KeyboardModificationMeta',
    'KeyboardBuildingState',
    'keyboard_to_html',
]

from typing import (
    Any,
    Union,
    Literal,
    Mapping,
    Callable,
    Awaitable,
    ParamSpec,
    Concatenate,
    MutableSequence,
)
from dataclasses import field as dataclass_field, dataclass

from pydantic.dataclasses import dataclass as pydantic_dataclass
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.telegram.ui.button import Button
from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.ui.exceptions import (
    KeyboardBlockBuildingError,
    KeyboardBlockModificationError,
)
from hubplatform.telegram.callback_data.hash import HashService


_P = ParamSpec('_P', default=...)
Keyboard = MutableSequence[MutableSequence['Button']]
KeyboardSpecBuilder = Callable[..., Awaitable[Keyboard]] | Callable[..., Keyboard]
KeyboardModificationCallable = Union[
    Callable[
        Concatenate['KeyboardBuildingState', _P],
        Awaitable[Union['KeyboardBuildingState', 'Keyboard']],
    ],
]


def _validate_keyboard(keyboard: Keyboard) -> None:
    if not isinstance(keyboard, MutableSequence):
        raise TypeError(
            f'Unexpected keyboard type. Expected: `MutableSequence[MutableSequence[Button]]`, '
            f'got: {keyboard.__class__.__name__!r}'
        )

    for line_index, line in enumerate(keyboard):
        if not isinstance(line, MutableSequence):
            raise TypeError(
                f'Unexpected buttons line type at line {line_index}. '
                f'Expected: `MutableSequence[Button]`, got: {line.__class__.__name__!r}.'
            )

        for button_index, button in enumerate(line):
            if not isinstance(button, Button):
                raise TypeError(
                    f'Unexpected button type at line {line_index} at position {button_index}. '
                    f'Expected: `Button`, got: {button.__class__.__name__!r}.'
                )


class KeyboardBlockSpec:
    def __init__(
        self, block_id: str, builder: KeyboardSpecBuilder | CallableWrapper[Keyboard]
    ) -> None:
        if not isinstance(block_id, str):
            raise TypeError('Block ID must be a string.')

        self._block_id = block_id
        self._builder: CallableWrapper[Keyboard] = (
            builder if isinstance(builder, CallableWrapper) else CallableWrapper(builder)
        )
        self._modifications: list[KeyboardModificationMeta] = []

    @property
    def block_id(self) -> str:
        return self._block_id

    def modify_with(
        self, modification_id: str, modification: KeyboardModificationCallable
    ) -> None:
        self._modifications.append(
            KeyboardModificationMeta(
                modification_id=modification_id,
                callable=modification,
            )
        )

    async def build(self, di_context: Mapping[str, Any]) -> _KeyboardBuildingResult:
        try:
            keyboard = await self._builder(data=di_context)
            state = KeyboardBuildingState(
                keyboard=keyboard, pending_modifications=self._modifications.copy()
            )
        except Exception as e:
            raise KeyboardBlockBuildingError(block_id=self.block_id) from e

        while True:
            if not state.pending_modifications:
                break
            mod = state.pending_modifications.pop(0)
            try:
                state = await mod.build(state, di_context)
            except KeyboardBlockBuildingError:
                raise
            except Exception as e:
                raise KeyboardBlockModificationError(
                    block_id=self.block_id, modification_id=mod.modification_id
                ) from e

        return _KeyboardBuildingResult(keyboard=state.keyboard)

    @classmethod
    def callback_button(
        cls,
        *,
        block_id: str,
        button_id: str | None = None,
        text: str,
        callback_data: CallbackData | str,
        style: Literal['danger', 'success', 'primary'] | None = None,
        pack_compact: bool = False,
        compress: bool = True,
        compression_version: str | None = None,
        hash: bool = True,
    ) -> KeyboardBlockSpec:
        async def build() -> Keyboard:
            return [
                [
                    Button(
                        button_id=button_id or block_id,
                        text=text,
                        callback_data=callback_data,
                        style=style,
                        pack_compact=pack_compact,
                        compress=compress,
                        compression_version=compression_version,
                        hash=hash,
                    )
                ]
            ]

        return KeyboardBlockSpec(block_id, builder=build)

    @classmethod
    def copy_text_button(
        cls,
        *,
        block_id: str,
        button_id: str | None = None,
        text: str,
        copy_text: str,
        style: Literal['danger', 'success', 'primary'] | None = None,
    ) -> KeyboardBlockSpec:
        async def build() -> Keyboard:
            return [
                [
                    Button(
                        button_id=button_id or block_id,
                        text=text,
                        copy_text=copy_text,
                        style=style,
                    )
                ]
            ]

        return KeyboardBlockSpec(block_id, builder=build)

    @classmethod
    def url_button(
        cls,
        *,
        block_id: str,
        button_id: str | None = None,
        text: str,
        url: str,
        style: Literal['danger', 'success', 'primary'] | None = None,
    ) -> KeyboardBlockSpec:
        async def build() -> Keyboard:
            return [
                [
                    Button(
                        button_id=button_id or block_id,
                        text=text,
                        url=url,
                        style=style,
                    )
                ]
            ]

        return KeyboardBlockSpec(block_id, builder=build)


@pydantic_dataclass(frozen=True)
class KeyboardModificationMeta:
    _wrapped: CallableWrapper[Keyboard | KeyboardBuildingState] = dataclass_field(init=False)
    modification_id: str
    callable: KeyboardModificationCallable

    def __post_init__(self) -> None:
        object.__setattr__(self, '_wrapped', CallableWrapper(self.callable))

    async def build(
        self, state: KeyboardBuildingState, di_context: Mapping[str, Any]
    ) -> KeyboardBuildingState:
        result = await self._wrapped(args=[state], data=di_context)
        if isinstance(result, KeyboardBuildingState):
            return result
        return KeyboardBuildingState(
            keyboard=result, pending_modifications=state.pending_modifications
        )


@pydantic_dataclass()
class KeyboardBuildingState:
    keyboard: Keyboard
    pending_modifications: list[KeyboardModificationMeta]

    def __post_init__(self) -> None:
        _validate_keyboard(self.keyboard)


@dataclass
class _KeyboardBuildingResult:
    keyboard: Keyboard

    def __post_init__(self) -> None:
        _validate_keyboard(self.keyboard)


def keyboard_to_html(keyboard: Keyboard, hash_service: HashService | None = None) -> str:
    result = []
    for line in keyboard:
        result.append(
            '<tg-button-row align="center">\n'
            + '\n'.join(i._to_html(hash_service=hash_service) for i in line)
            + '\n</tg-button-row>'
        )
    return '\n'.join(result)
