from __future__ import annotations


__all__ = [
    'CallbackDataUnpackError',
    'InvalidPositionalCallbackDataError',
    'CallbackDataPackError',
    'NotSerializableValueError',
    'PositionalContextNotSupportedError',
    'CallbackIdentifierMismatchError',
    'BadCallbackIdentifierError',
]

from .base import TelegramError


# BASE EXCEPTIONS
class CallbackDataError(TelegramError):
    ...


class CallbackDataUnpackError(CallbackDataError):
    """Raised when callback data cannot be parsed or validated."""


class CallbackDataPackError(CallbackDataError):
    """Raised when a callback payload cannot be serialized."""


# REAL EXCEPTIONS
# Parsing exceptions
class InvalidPositionalCallbackDataError(CallbackDataUnpackError):
    """Raised when callback data does not use the positional wire format."""


class CallbackIdentifierMismatchError(CallbackDataUnpackError):
    """Raised when an envelope identifier differs from the target model identifier."""


class BadCallbackIdentifierError(CallbackDataError):
    """Raised when a callback identifier does not match the re `[a-zA-Z0-9\\._-]`. """


# Packing exceptions
class NotSerializableValueError(CallbackDataPackError):
    """Raised when a value is unsupported by the positional serializer."""


class PositionalContextNotSupportedError(CallbackDataPackError):
    """Raised when a positional envelope would discard callback context."""


class PositionalCallbackTooLong(CallbackDataPackError):
    """Raise when a total callback string is longer then 64 bytes."""
