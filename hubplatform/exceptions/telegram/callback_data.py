from __future__ import annotations


__all__ = [
    'CallbackDataParsingError',
    'NotPositionalDataError',
    'CallbackDataPackError',
    'NotSerializableValueError',
    'PositionalCallbackWithContextError',
    'IdentifierMismatchError',
]

from .base import TelegramError


# BASE EXCEPTIONS
class CallbackDataParsingError(TelegramError):
    """Raised when callback data cannot be parsed or validated."""


class CallbackDataPackError(TelegramError):
    """Raised when a callback payload cannot be serialized."""


# REAL EXCEPTIONS
# Parsing exceptions
class NotPositionalDataError(CallbackDataParsingError):
    """Raised when callback data does not use the positional wire format."""


class IdentifierMismatchError(CallbackDataParsingError):
    """Raised when an envelope identifier differs from the target model identifier."""


# Packing exceptions
class NotSerializableValueError(CallbackDataPackError):
    """Raised when a value is unsupported by the positional serializer."""


class PositionalCallbackWithContextError(CallbackDataPackError):
    """Raised when a positional envelope would discard callback context."""
