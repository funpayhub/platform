from __future__ import annotations


__all__ = [
    'GoodsError',
    'NotEnoughGoodsError',
    'GoodsSourceNotFoundError',
]

from hubplatform.exceptions import HubPlatformError


class GoodsError(HubPlatformError):
    pass


class NotEnoughGoodsError(GoodsError):
    pass


class GoodsSourceNotFoundError(GoodsError):
    pass
