from __future__ import annotations


__all__ = [
    'GeneralActionContext',
    'GeneralOrderContext',
    'GeneralReviewContext',
    'GeneralMessageContext',
]

from pydantic import BaseModel

from hubplatform.i18n import I18nString
from hubplatform.expressions.call_context import ExpressionContext


class GeneralActionContext(
    ExpressionContext,
    BaseModel,
    name=I18nString(
        'hubplatform.expressions.contexts.general_action:name',
        'Общее действие',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_action:description',
        'Выражения в этом контексте могут использоваться, когда пользователь совершил '
        'действие на маркетплейсе: отправил сообщение, сделал заказ, оставил отзыв и т.д.',
    ),
):
    initiator_id: str
    initiator_username: str
    marketplace_id: str


class GeneralOrderContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_order:name',
        'Заказ',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_order:description',
        'Выражения в этом контексте могут использоваться в тексте, '
        'связанном с заказом на маркетплейсе.',
    ),
):
    order_id: str
    order_name: str
    order_amount: int


class GeneralReviewContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_review:name',
        'Отзыв',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_review:description',
        'Выражения в этом контексте могут использоваться в тексте, связанном с отзывом на заказ.',
    ),
):
    order_id: str
    review_rating: int
    review_text: str


class GeneralMessageContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_message:name',
        'Сообщение',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_message:description',
        'Выражения в этом контексте могут использоваться в тексте, '
        'связанном с сообщением пользователя.',
    ),
):
    message_id: str
    message_text: str
