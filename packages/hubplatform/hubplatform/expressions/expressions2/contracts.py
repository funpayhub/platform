"""Small shared contracts that independent components can choose to supply."""

from __future__ import annotations

from dataclasses import dataclass

from .capabilities import Capability


@dataclass(frozen=True)
class OrderReference:
    """Identity of an order, independent of its marketplace's native model.

    ``marketplace`` is a stable machine name, such as ``funpay``. Components
    normalize native order IDs to strings. ``account_id`` distinguishes seller
    accounts when marketplace + order ID alone is insufficient. A plugin's
    persistence key must use the same identity fields as its event handlers.

    This intentionally promises no common price, buyer, status, or order API.
    Introduce additional shared contracts only when there is a real consumer.
    """

    marketplace: str
    order_id: str
    account_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in (('marketplace', self.marketplace), ('order_id', self.order_id)):
            if not isinstance(value, str) or not value:
                raise ValueError(f'OrderReference.{name} must be a nonempty string.')
        if self.account_id is not None and (
            not isinstance(self.account_id, str) or not self.account_id
        ):
            raise ValueError('OrderReference.account_id must be None or a nonempty string.')


ORDER_REFERENCE = Capability('hubplatform.order_reference', OrderReference)
