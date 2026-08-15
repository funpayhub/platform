from __future__ import annotations


__all__ = [
    'Button',
    'Keyboard',
    'KeyboardBlockSpec',
    'KeyboardModification',
    'KeyboardBuildingState',
    'MenuSpec',
    'RenderedMenu',
    'MenuContext',
    'MenuContextSnapshot',
]

from typing import TYPE_CHECKING, Any, Self, Literal, ParamSpec, Concatenate
from dataclasses import field, dataclass
from collections.abc import Mapping, Callable, Awaitable

from pydantic import Field, BaseModel
from aiogram.types import CopyTextButton, InlineKeyboardButton
from eventry.asyncio.callable_wrappers import CallableWrapper

from hubplatform.telegram.callback_data import CallbackData
from hubplatform.core.pydantic_serializable import pydantic_fallback_serializer
from hubplatform.telegram.callback_data.hash import HashService


if TYPE_CHECKING:
    from aiogram.types import LoginUrl, WebAppInfo, CallbackGame


_P = ParamSpec('_P')
Keyboard = list[list['Button']]
KeyboardSpecBuilder = Callable[..., Awaitable[Keyboard]] | Callable[..., Keyboard]
KeyboardModificationCallable = (
    Callable[Concatenate['KeyboardBuildingState', _P], Awaitable['KeyboardBuildingState']]
    | Callable[Concatenate['KeyboardBuildingState', _P], 'KeyboardBuildingState']
)
MenuFinalizer = (
    Callable[Concatenate['MenuSpec', _P], Awaitable['MenuSpec']]
    | Callable[Concatenate['MenuSpec', _P], 'MenuSpec']
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
        callback_data: str | None = None
        if self.callback_data is not None:
            if self.hash and hash_service is None:
                raise ValueError(
                    f'Cannot render button {self.button_id}. '
                    'Button requires to hash its `callback_data`, '
                    'but hash_service was not provided.'
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
                callback_data = hash_service.hash(cb)

        return InlineKeyboardButton(
            text=self.text,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
            style=self.style,
            url=self.url,
            callback_data=callback_data,
            web_app=self.web_app,
            login_url=self.login_url,
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
        self._modifications: list[KeyboardModification] = []

    @property
    def block_id(self) -> str:
        return self._block_id

    def modify_with(
        self, modification_id: str, modification: KeyboardModificationCallable
    ) -> None:
        self._modifications.append(
            KeyboardModification(
                modification_id=modification_id,
                modification_callable=modification,
            )
        )

    async def build(
        self,
        app_context: Mapping[str, Any],
        hash_service: HashService | None = None,
    ) -> list[list[InlineKeyboardButton]]:
        try:
            initial_keyboard = await self._builder(data=app_context)
        except Exception as e:
            raise Exception(
                f'An error occurred while building button {self.block_id}'
            ) from e  # todo: button build exception

        buttons = initial_keyboard
        pending_mods = self._modifications.copy()
        while pending_mods:
            modification = pending_mods.pop()
            try:
                new_block = KeyboardBuildingState(
                    buttons=buttons, pending_modifications=pending_mods.copy()
                )
                wrapped = CallableWrapper(modification.modification_callable)
                block = await wrapped(args=(new_block,), data=app_context)
                buttons = block.buttons
                pending_mods = block.pending_modifications
            except Exception:
                import traceback

                print(traceback.format_exc())
                # todo: normal logging
                continue

        result = []
        for line in buttons:
            result_line = []
            for button in line:
                result_line.append(button.render(hash_service=hash_service))
            result.append(result_line)
        return result

    @classmethod
    def callback_button(
        cls,
        *,
        block_id: str,
        button_id: str | None = None,
        text: str,
        callback_data: CallbackData,
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
class KeyboardModification:
    modification_id: str
    modification_callable: KeyboardModificationCallable


@dataclass
class KeyboardBuildingState:
    buttons: list[list[Button]]
    pending_modifications: list[KeyboardModification]


class MenuSpec(BaseModel):
    header_text: str = ''
    header_body_sep: str = '\n\n'
    body_text: str = ''
    body_footer_sep: str = '\n\n'
    footer_text: str = ''
    header_footer_sep: str = '\n\n'
    header_keyboard: list[KeyboardBlockSpec] = field(default_factory=list)
    main_keyboard: list[KeyboardBlockSpec] = field(default_factory=list)
    footer_keyboard: list[KeyboardBlockSpec] = field(default_factory=list)
    finalizer: MenuFinalizer | None = None

    def total_blocks(self) -> list[KeyboardBlockSpec]:
        return [
            *self.header_keyboard,
            *self.main_keyboard,
            *self.footer_keyboard,
        ]

    async def render(
        self, app_context: Mapping[str, Any], hash_service: HashService | None = None
    ) -> RenderedMenu:
        keyboard = []
        for block in self.total_blocks():
            result = await block.build(app_context, hash_service=hash_service)
            keyboard.extend(result)

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

        return RenderedMenu(text=text, keyboard=keyboard)


@dataclass
class RenderedMenu:
    text: str
    keyboard: list[list[InlineKeyboardButton]]


class MenuContextSnapshot(BaseModel):
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
