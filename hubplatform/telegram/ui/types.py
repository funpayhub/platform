from __future__ import annotations


__all__ = [
    'Button',
    'Keyboard',
    'KeyboardBlockSpec',
    'KeyboardModificationMeta',
    'KeyboardBuildingState',
    'MenuSpec',
    'RenderedMenu',
    'MenuContext',
    'MenuContextSnapshot',
]

from typing import Any, Self, Union, Literal, ParamSpec, Concatenate
from dataclasses import field as dataclass_field, dataclass
from collections.abc import Mapping, Callable, Awaitable, MutableSequence

from pydantic import Field, BaseModel, ConfigDict
from aiogram.types import LoginUrl, WebAppInfo, CallbackGame, CopyTextButton, InlineKeyboardButton
from pydantic.dataclasses import dataclass as pydantic_dataclass
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.logging.loggers import telegram as _logger
from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.ui.exceptions import (
    ButtonRenderError,
    KeyboardBlockBuildingError,
    KeyboardBlockModificationError,
)
from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer
from hubplatform.telegram.callback_data.hash import HashService


logger = _logger.ui

_P = ParamSpec('_P', default=...)
Keyboard = MutableSequence[MutableSequence['Button']]
KeyboardSpecBuilder = Callable[..., Awaitable[Keyboard]] | Callable[..., Keyboard]
KeyboardModificationCallable = Union[
    Callable[
        Concatenate['KeyboardBuildingState', _P],
        Awaitable[Union['KeyboardBuildingState', 'Keyboard']],
    ],
    Callable[Concatenate['KeyboardBuildingState', _P], Union['KeyboardBuildingState', 'Keyboard']],
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


class Button(BaseModel):
    button_id: str
    """Button ID."""

    text: str
    """Label text on the button"""

    icon_custom_emoji_id: str | None = None
    """Unique identifier of the custom emoji shown before the text of the button. 
    Can only be used by bots that purchased additional usernames on 
    `Fragment <https://fragment.com>`_ or in the messages directly sent by the bot to private, 
    group and supergroup chats if the owner of the bot has a Telegram Premium subscription
    """

    style: str | None = None
    """Style of the button. 
    Must be one of 'danger' (red), 'success' (green) or 'primary' (blue). 
    If omitted, then an app-specific style is used
    """

    url: str | None = None
    """HTTP or tg:// URL to be opened when the button is pressed. 
    Links :code:`tg://user?id=<user_id>` can be used to mention a user by their identifier 
    without using a username, if this is allowed by their privacy settings
    """

    callback_data: str | CallbackData | None = None
    """Data to be sent in a `callback query <https://core.telegram.org/bots/api#callbackquery>`_ 
    to the bot when the button is pressed.
    """

    pack_compact: bool = False
    """*Optional*. Whether to use compact packing algorithm for buttons callback or not.
    Does not uses if `callback_data` is a string.
    """

    compress: bool = True
    """*Optional*. Whether to compress packed `callback_data` or not.
    Does not uses if `callback_data` is a string.
    """

    compression_version: str | None = None
    """*Optional*. Use specific compression version. If `None`_, an apps default compression 
    version will be used.
    Does not uses if `callback_data` is a string.
    """

    hash: bool = True
    """*Optional*. Whether to hash and store value into callback_data database or not."""

    web_app: WebAppInfo | None = None
    """Description of the `Web App <https://core.telegram.org/bots/webapps>`_ that will be 
    launched when the user presses the button. The Web App will be able to send an arbitrary 
    message on behalf of the user using the method 
    :class:`aiogram.methods.answer_web_app_query.AnswerWebAppQuery`. 
    Available only in private chats between a user and the bot. 
    Not supported for messages sent on behalf of a business account
    """

    login_url: LoginUrl | None = None
    """An HTTPS URL used to automatically authorize the user. 
    Can be used as a replacement for the 
    `Telegram Login Widget <https://core.telegram.org/widgets/login>`_
    """

    copy_text: CopyTextButton | None = None
    """Description of the button that copies the specified text to the clipboard"""

    callback_game: CallbackGame | None = None
    """Description of the game that will be launched when the user presses the button"""

    pay: bool | None = None
    """Specify :code:`True`, to send a `Pay button <https://core.telegram.org/bots/api#payments>`_. 
    Substrings '⭐' and 'XTR' in the buttons's text will be replaced with a Telegram Star icon.
    """

    def render(self, hash_service: HashService | None = None) -> InlineKeyboardButton:
        try:
            return self._render(hash_service=hash_service)
        except ButtonRenderError:
            raise
        except Exception as e:
            raise ButtonRenderError(button_id=self.button_id) from e

    def _render(self, hash_service: HashService | None = None) -> InlineKeyboardButton:
        callback_data: str | None = None
        if self.callback_data is not None:
            if self.hash and hash_service is None:
                raise ButtonRenderError(
                    button_id=self.button_id,
                    message=f'Cannot render button {self.button_id}. '
                    'Button requires to hash its `callback_data`, '
                    'but hash_service was not provided.',
                )

            if isinstance(self.callback_data, CallbackData):
                method = (
                    self.callback_data.pack_compact
                    if self.pack_compact
                    else self.callback_data.pack
                )
                cb = method(compress=self.compress, compression_version=self.compression_version)
            else:
                cb = self.callback_data

            if self.hash:
                cb = hash_service.hash(cb)

            callback_data = cb

        return InlineKeyboardButton(
            text=self.text,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
            style=self.style,
            url=self.url,
            callback_data=callback_data,
            web_app=self.web_app,
            login_url=self.login_url,
            copy_text=self.copy_text,
            callback_game=self.callback_game,
            pay=self.pay,
        )


class KeyboardBlockSpec:
    def __init__(
        self, block_id: str, builder: KeyboardSpecBuilder | CallableWrapper[Keyboard]
    ) -> None:
        if not isinstance(block_id, str):
            raise TypeError('Button ID must be a string.')

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

    async def build(self, di_context: Mapping[str, Any]) -> KeyboardBlockBuildingResult:
        try:
            keyboard = await self._builder(data=di_context)
            _validate_keyboard(keyboard)
        except Exception as e:
            raise KeyboardBlockBuildingError(block_id=self.block_id) from e

        keyboard = keyboard
        pending_mods = self._modifications.copy()
        errors = []
        while pending_mods:
            modification = pending_mods.pop(0)
            try:
                state = KeyboardBuildingState(
                    keyboard=keyboard, pending_modifications=pending_mods
                )
                result = await modification.build(state, di_context)
                if isinstance(result, KeyboardBuildingState):
                    keyboard = result.keyboard
                    pending_mods = result.pending_modifications
                else:
                    keyboard = result
            except KeyboardBlockModificationError as e:
                errors.append(e)
            except Exception as e:
                new_e = KeyboardBlockModificationError(
                    block_id=self.block_id, modification_id=modification.modification_id
                )
                new_e.__cause__ = e
                errors.append(new_e)
        return KeyboardBlockBuildingResult(keyboard=keyboard, errors=errors)

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
                        copy_text=CopyTextButton(text=copy_text),
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


@dataclass(frozen=True)
class KeyboardModificationMeta:
    _wrapped: CallableWrapper[Keyboard | KeyboardBuildingState] = dataclass_field(init=False)
    modification_id: str
    callable: KeyboardModificationCallable

    def __post_init__(self) -> None:
        object.__setattr__(self, '_wrapped', CallableWrapper(self.callable))

    async def build(
        self, state: KeyboardBuildingState, di_context: Mapping[str, Any]
    ) -> KeyboardBuildingState | Keyboard:
        result = await self._wrapped(args=[state], data=di_context)
        if isinstance(result, KeyboardBuildingState):
            return result
        _validate_keyboard(result)
        return result


@dataclass
class KeyboardBuildingState:
    keyboard: Keyboard
    pending_modifications: list[KeyboardModificationMeta]

    def __post_init__(self) -> None:
        _validate_keyboard(self.keyboard)


@dataclass
class KeyboardBlockBuildingResult:
    keyboard: Keyboard
    errors: list[KeyboardBlockModificationError] = dataclass_field(default_factory=list)


@pydantic_dataclass(
    config=ConfigDict(arbitrary_types_allowed=True, validate_assignment=True),
    validate_on_init=True,
)
class MenuSpec:
    menu_id: str
    header_text: str = ''
    header_body_sep: str = '\n\n'
    body_text: str = ''
    body_footer_sep: str = '\n\n'
    footer_text: str = ''
    header_footer_sep: str = '\n\n'
    header_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)
    main_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)
    footer_keyboard: MutableSequence[KeyboardBlockSpec] = dataclass_field(default_factory=list)

    @property
    def total_blocks(self) -> list[KeyboardBlockSpec]:
        return [
            *self.header_keyboard,
            *self.main_keyboard,
            *self.footer_keyboard,
        ]

    async def render(
        self,
        di_context: Mapping[str, Any],
        hash_service: HashService | None = None,
    ) -> RenderedMenu:
        building_errors: list[KeyboardBlockBuildingError] = []
        keyboard: Keyboard = []

        for block in self.total_blocks:
            try:
                result = await block.build(di_context)
                keyboard.extend(result.keyboard)
                building_errors.extend(result.errors)
            except KeyboardBlockBuildingError as e:
                building_errors.append(e)
            except Exception as e:
                new_e = KeyboardBlockBuildingError(block_id=block.block_id)
                new_e.__cause__ = e
                building_errors.append(new_e)

        converted_keyboard: list[list[InlineKeyboardButton]] = []
        render_errors: list[ButtonRenderError] = []
        for line in keyboard:
            result_line = []
            for button in line:
                try:
                    result_line.append(button.render(hash_service=hash_service))
                except ButtonRenderError as e:
                    render_errors.append(e)
                except Exception as e:
                    new_e = ButtonRenderError(button_id=button.button_id)
                    new_e.__cause__ = e
                    render_errors.append(new_e)
            if result_line:
                converted_keyboard.append(result_line)

        text = self.header_text
        if self.body_text:
            if text:
                text += self.header_body_sep
            text += self.body_text
        if self.footer_text:
            if self.body_text:
                text += self.body_footer_sep
            elif self.header_text:
                text += self.header_footer_sep
            text += self.footer_text

        return RenderedMenu(
            text=text,
            keyboard=converted_keyboard,
            building_errors=building_errors,
            render_errors=render_errors,
        )


@pydantic_dataclass
class RenderedMenu:
    text: str
    keyboard: list[list[InlineKeyboardButton]]
    building_errors: list[KeyboardBlockBuildingError] = Field(default_factory=list)
    render_errors: list[ButtonRenderError] = Field(default_factory=list)


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

    def snapshot(self) -> MenuContextSnapshot:
        fields = self._dump_context_fields()
        data = fields.pop('data', {})
        return MenuContextSnapshot(
            menu_id=self.menu_id,
            keyboard_page=self.keyboard_page,
            text_page=self.text_page,
            fields=fields,
            data=data,
        )

    @classmethod
    def from_snapshot(cls, envelope: MenuContextSnapshot) -> Self:
        return cls.model_validate(
            envelope.fields
            | {
                'menu_id': envelope.menu_id,
                'keyboard_page': envelope.keyboard_page,
                'text_page': envelope.text_page,
                'data': envelope.data,
            }
        )


class MenuContextSnapshot(BaseModel):
    menu_id: str
    keyboard_page: int
    text_page: int
    data: dict[str, Any]
    fields: dict[str, Any]
