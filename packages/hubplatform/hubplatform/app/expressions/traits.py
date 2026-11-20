"""Traits shared by every marketplace.

A handler puts the traits of an event into a container::

    TraitsContainer(
        FunPayOrderTrait(order_id=..., order_name=..., order_amount=..., order=...),
        InitiatorTrait(initiator_id=..., initiator_username=...),
    )

A marketplace component refines a trait by subclassing it (a FunPay order is an order), so the
generic expressions keep working and FunPay-specific expressions can require the subclass.
"""

from __future__ import annotations


__all__ = [
    'InitiatorTrait',
    'OrderTrait',
    'ReviewTrait',
    'MessageTrait',
]

from hubplatform.i18n import I18nString
from hubplatform.expressions.traits import Trait


class InitiatorTrait(
    Trait,
    name=I18nString('hubplatform.expressions.traits.initiator:name', 'Пользователь'),
    description=I18nString(
        'hubplatform.expressions.traits.initiator:description',
        'Пользователь, который совершил действие, например написал сообщение, '
        'оформил заказ или оставил отзыв',
    ),
):
    initiator_id: str
    initiator_username: str


class OrderTrait(
    Trait,
    name=I18nString('hubplatform.expressions.traits.order:name', 'Заказ'),
    description=I18nString(
        'hubplatform.expressions.traits.order:description',
        'Заказ на любой торговой площадке, например новый заказ, заказ с измененным статусом '
        'или заказ, о котором оставили отзыв',
    ),
):
    order_id: str
    order_name: str
    order_amount: int


class ReviewTrait(
    Trait,
    name=I18nString('hubplatform.expressions.traits.review:name', 'Отзыв'),
    description=I18nString(
        'hubplatform.expressions.traits.review:description',
        'Отзыв на любой торговой площадке, например новый или измененный отзыв',
    ),
):
    review_rating: int
    review_text: str


class MessageTrait(
    Trait,
    name=I18nString('hubplatform.expressions.traits.message:name', 'Сообщение'),
    description=I18nString(
        'hubplatform.expressions.traits.message:description',
        'Сообщение на любой торговой площадке',
    ),
):
    message_id: str
    message_text: str
