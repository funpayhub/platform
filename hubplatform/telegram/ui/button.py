from __future__ import annotations


__all__ = ['Button']


from pydantic import BaseModel
from aiogram.types import LoginUrl, WebAppInfo, CallbackGame, CopyTextButton, InlineKeyboardButton

from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.ui.exceptions import ButtonRenderError
from hubplatform.telegram.callback_data.hash import HashService


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
    Links :code:`tg://user?menu_id=<user_id>` can be used to mention a user by their identifier 
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
                cb = hash_service.hash(cb)  # type: ignore[union-attr]  # check above

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
