from __future__ import annotations


__all__ = [
    'telegram',
    'app',
]

from logging import getLogger


class telegram:  # noqa: N801
    ui = getLogger('hubplatform.telegram.ui')


class app:  # noqa: N801
    main = getLogger('hubplatform.app.main')
