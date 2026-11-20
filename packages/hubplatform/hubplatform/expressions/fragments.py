from __future__ import annotations


__all__ = ['Fragment', 'EvaluatedPart', 'fragment_to_text']


class Fragment:
    """Base class for expression results that are not text: images, message breaks, files, ...

    ``ExpressionsManager.evaluate()`` keeps a fragment returned by a top-level call as an object,
    so the code that sends the result decides what to do with it. For example, a platform that
    cannot send text and an image in one message splits the result into several messages.

    Where only text can be used, ``EvaluationResult.text`` replaces a fragment with
    ``text_fallback()``.
    """

    def text_fallback(self) -> str:
        """Text that replaces the fragment where only text can be used. Empty by default."""
        return ''


type EvaluatedPart = str | Fragment
"""A part of an evaluated string: text or a fragment."""


def fragment_to_text(part: EvaluatedPart) -> str:
    """Returns ``part`` as text: a string as-is, a fragment as its text fallback."""
    return part if isinstance(part, str) else part.text_fallback()
