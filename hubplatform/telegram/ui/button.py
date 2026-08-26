from __future__ import annotations


__all__ = ['Button']

import html

from pydantic import BaseModel

from hubplatform.telegram.callback_data import CallbackData
from hubplatform.telegram.ui.exceptions import ButtonRenderError
from hubplatform.telegram.callback_data.hash import HashService


class Button(BaseModel):
    button_id: str
    """Button ID."""

    text: str
    """Label text on the button"""

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

    copy_text: str | None = None
    """Description of the button that copies the specified text to the clipboard"""

    disabled: bool = False

    def to_html(self, hash_service: HashService | None = None) -> str:
        try:
            return self._to_html(hash_service=hash_service)
        except ButtonRenderError:
            raise
        except Exception as e:
            raise ButtonRenderError(button_id=self.button_id) from e

    def _to_html(self, hash_service: HashService | None = None) -> str:
        attributes = {}
        if self.disabled:
            attributes['type'] = 'disabled'
        elif self.callback_data is not None:
            attributes['type'] = 'callback_data'
            attributes['data'] = self._pack_callback(hash_service=hash_service)
        elif self.copy_text is not None:
            attributes['type'] = 'copy_text'
            attributes['text'] = self.copy_text
        elif self.url is not None:
            attributes['type'] = 'url'
            attributes['url'] = self.url
        else:
            raise ButtonRenderError(button_id=self.button_id, message='Unknown button type.')

        if self.style is not None:
            attributes['style'] = self.style

        return (
            '<tg-button '
            + ' '.join(f'{k}="{html.escape(v)}"' for k, v in attributes.items())
            + f'>{self.text}</tg-button>'
        )

    def _pack_callback(self, hash_service: HashService | None = None) -> str:
        if self.callback_data is None:
            raise Exception()  # todo

        if self.hash and hash_service is None:
            raise ButtonRenderError(
                button_id=self.button_id,
                message=f'Cannot render button {self.button_id}. '
                'Button requires to hash its `callback_data`, '
                'but hash_service was not provided.',
            )

        if isinstance(self.callback_data, CallbackData):
            method = (
                self.callback_data.pack_compact if self.pack_compact else self.callback_data.pack
            )
            cb = method(compress=self.compress, compression_version=self.compression_version)
        else:
            cb = self.callback_data

        if self.hash:
            cb = hash_service.hash(cb)  # type: ignore[union-attr]  # check above

        return cb
