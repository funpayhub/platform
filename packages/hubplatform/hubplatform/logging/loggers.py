from __future__ import annotations


__all__ = [
    'telegram',
    'app',
    'updates',
    'expressions',
]

from logging import getLogger


class telegram:  # noqa: N801
    ui = getLogger('hubplatform.telegram.ui')


class app:  # noqa: N801
    main = getLogger('hubplatform.app.main')


class updates:  # noqa: N801
    installer = getLogger('hubplatform.updates.installer')


class expressions:  # noqa: N801
    manager = getLogger('hubplatform.expressions.manager')
