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
        'Базовый контекст события',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_action:description',
        'Выражения в этом контексте могут быть использованы, когда произошло какое-либо событие '
        'на любой торговой площадке: вы получили новое сообщение, новый заказ, новый отзыв и т.д.',
    ),
):
    initiator_id: str
    initiator_username: str
    marketplace_id: str


class GeneralOrderContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_order:name',
        'Контекст заказа',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_order:description',
        'Выражения в этом контексте могут быть использованы, когда произошло какое-то событие, '
        'связанное с заказами, на любой торговой площадке. '
        'Например: новый заказ, изменение статуса заказа и т.д.',
    ),
):
    order_id: str
    order_name: str
    order_amount: int


class GeneralReviewContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_review:name',
        'Контекст отзыва',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_review:description',
        'Выражения в этом контексте могут быть использованы, когда произошло какое-то событие, '
        'связанное с отзывами, на любой торговой площадке. '
        'Например: новый отзыв, изменение отзыва и т.д.',
    ),
):
    order_id: str
    review_rating: int
    review_text: str


class GeneralMessageContext(
    GeneralActionContext,
    name=I18nString(
        'hubplatform.expressions.contexts.general_message:name',
        'Контекст сообщения',
    ),
    description=I18nString(
        'hubplatform.expressions.contexts.general_message:description',
        'Выражения в этом контексте могут использоваться в тексте, '
        'Выражения в этом контексте могут быть использованы, когда произошло какое-то событие, '
        'связанное с сообщениями, на любой торговой площадке. '
        'Например: новое сообщение и т.д.',
    ),
):
    message_id: str
    message_text: str
