from __future__ import annotations


__all__ = [
    'telegram',
]

from logging import getLogger


class _Telegram:
    ui = getLogger('hubplatform.telegram.ui')


telegram = _Telegram()
