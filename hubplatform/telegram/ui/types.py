from __future__ import annotations

from typing import Any, Self, Literal, ParamSpec, Concatenate
from dataclasses import dataclass
from collections.abc import Callable, Awaitable

from pydantic import Field, BaseModel
from aiogram.types import CopyTextButton, InlineKeyboardButton
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.telegram.callback_data import CallbackData
from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer
from hubplatform.telegram.callback_data.hash import HashService


P = ParamSpec('P')
ButtonType = InlineKeyboardButton
ButtonsRow = list[InlineKeyboardButton]
Buttons = ButtonType | ButtonsRow
ButtonBuilder = Callable[..., Awaitable[Buttons]] | CallableWrapper[Buttons]
ButtonModification = Callable[Concatenate[ButtonsRow, P], Buttons] | CallableWrapper[Buttons]


@dataclass(frozen=True)
class ButtonSpecModification:
    id: str
    modification: CallableWrapper[Buttons]


class ButtonSpec:
    def __init__(self, button_id: str, builder: ButtonBuilder) -> None:
        if not isinstance(button_id, str):
            raise TypeError('Button ID must be a string.')

        self._button_id = button_id
        self._builder = (
            builder if isinstance(builder, CallableWrapper) else CallableWrapper(builder)
        )
        self._modifications: list[ButtonSpecModification] = []

    @property
    def button_id(self) -> str:
        return self._button_id

    def modify_with(self, id: str, modification: ButtonModification[P]) -> None:
        modification = (
            modification
            if isinstance(modification, CallableWrapper)
            else CallableWrapper(modification)
        )
        self._modifications.append(ButtonSpecModification(id, modification))

    async def build(self, data: dict[str, Any]) -> ButtonsRow:
        try:
            result = await self._builder(data=data)
        except Exception as e:
            raise Exception(
                f'An error occurred while building button {self.button_id}'
            ) from e  # todo: button build exception

        result_normalized = [result] if not isinstance(result, list) else result
        for index, btn in enumerate(result_normalized):
            if not isinstance(btn, InlineKeyboardButton):
                raise Exception(
                    f'Button builder {self.button_id} returned instance of '
                    f'{btn.__class__.__name__!r} at position {index}. '
                    f'Only `aiogram.types.InlineKeyboardButton` is allowed.'
                )

        for mod in self._modifications:
            old = [i.model_copy(deep=True) for i in result_normalized]
            try:
                mod_result = await mod.modification(args=(result_normalized,), data=data)
            except Exception:
                print(
                    f'An error occurred while running modificator {mod.id!r} '
                    f'for button {self.button_id!r}.'
                )
                import traceback

                print(traceback.format_exc())
                # todo: logging
                continue

            result_normalized = [mod_result] if not isinstance(mod_result, list) else mod_result
            for index, btn in enumerate(result_normalized):
                if not isinstance(btn, InlineKeyboardButton):
                    print(
                        f'Button modification {mod.id!r} for button {self.button_id!r} '
                        f'returned {btn.__class__.__name__!r} at position {index!r}. '
                        f'Only `aiogram.types.InlineKeyboardButton` is allowed.\n'
                        f'Skipping '
                    )  # todo: logging
                    result_normalized = old
                    break

        return result_normalized

    @classmethod
    def callback_button(
        cls,
        button_id: str,
        text: str,
        callback_data: CallbackData,
        style: Literal['danger', 'success', 'primary'] | None = None,
        pack_compact: bool = False,
        compress: bool = True,
        compress_version: str | None = None,
        hash: bool = True,
    ) -> ButtonSpec:
        async def build_button(hash_service: HashService) -> InlineKeyboardButton:
            method = callback_data.pack_compact if pack_compact else callback_data.pack
            result = method(compress=compress, compression_version=compress_version)
            if hash:
                result = hash_service.hash(result)

            return InlineKeyboardButton(
                text=text,
                callback_data=result,
                style=style,
            )

        return ButtonSpec(button_id, builder=build_button)

    @classmethod
    def copy_text_button(
        cls,
        button_id: str,
        text: str,
        copy_text: str,
        style: Literal['danger', 'success', 'primary'] | None = None,
    ) -> ButtonSpec:
        async def build_button() -> InlineKeyboardButton:
            return InlineKeyboardButton(
                text=text,
                copy_text=CopyTextButton(text=copy_text),
                style=style,
            )

        return ButtonSpec(button_id, builder=build_button)

    @classmethod
    def url_button(
        cls,
        button_id: str,
        text: str,
        url: str,
        style: Literal['danger', 'success', 'primary'] | None = None,
    ) -> ButtonSpec:
        async def build_button() -> InlineKeyboardButton:
            return InlineKeyboardButton(text=text, url=url, style=style)

        return ButtonSpec(button_id, builder=build_button)


class MenuBuilder:
    def __init__(self) -> None:
        self._menu: list[list[Any]] = []


class MenuContextEnvelope(BaseModel):
    menu_id: str
    keyboard_page: int
    text_page: int
    data: dict[str, Any]
    fields: dict[str, Any]


class MenuContext(BaseModel):
    menu_id: str
    keyboard_page: int = 0
    text_page: int = 0
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def _validate_menu_id(cls, menu_id: str) -> str:
        if not menu_id:
            raise ValueError('Menu ID cannot be empty.')

        return menu_id

    def _dump_context_fields(self) -> dict[str, Any]:
        return self.model_dump(
            mode='json',
            exclude=set(MenuContext.model_fields.keys()),
            fallback=pydantic_fallback_serializer,
        )

    def to_envelope(self) -> MenuContextEnvelope:
        fields = self._dump_context_fields()
        data = fields.pop('data', {})
        return MenuContextEnvelope(
            menu_id=self.menu_id,
            keyboard_page=self.keyboard_page,
            text_page=self.text_page,
            fields=fields,
            data=data,
        )

    @classmethod
    def from_envelope(cls, envelope: MenuContextEnvelope) -> Self:
        return cls.model_validate(
            envelope.fields
            | {
                'menu_id': envelope.menu_id,
                'keyboard_page': envelope.keyboard_page,
                'text_page': envelope.text_page,
                'data': envelope.data,
            }
        )
