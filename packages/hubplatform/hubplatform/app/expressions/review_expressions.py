from __future__ import annotations


__all__ = ['register_review_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.category import ExpressionsCategory
from hubplatform.expressions.definition import expression

from .contexts import GeneralReviewContext


CATEGORY = ('general', 'review')

_manager = ExpressionsManager({})
_manager.add_context(GeneralReviewContext, 'general_review')
_manager.add_category(
    CATEGORY,
    ExpressionsCategory(
        name=I18nString(
            'hubplatform.expressions.general:review:name',
            'Отзыв',
        ),
        description=I18nString(
            'hubplatform.expressions.general:review:description',
            'Данные отзыва, который оставил пользователь.',
        ),
    ),
)


@_manager.register(context_type=GeneralReviewContext, call_key='order_id', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:review.order_id:name',
            'ID заказа',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:review.order_id:description',
            'Идентификатор заказа, к которому относится отзыв. '
            'Пример: Спасибо за отзыв о заказе №$order_id!',
        ),
    )
)
async def order_id(ctx: GeneralReviewContext) -> str:
    return ctx.order_id


@_manager.register(context_type=GeneralReviewContext, call_key='review_rating', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:review.review_rating:name',
            'Оценка отзыва',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:review.review_rating:description',
            'Оценка, которую пользователь поставил в отзыве. '
            'Пример: Спасибо за оценку $review_rating!',
        ),
    )
)
async def review_rating(ctx: GeneralReviewContext) -> int:
    return ctx.review_rating


@_manager.register(context_type=GeneralReviewContext, call_key='review_text', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:review.review_text:name',
            'Текст отзыва',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:review.review_text:description',
            'Текст отзыва пользователя. Пример: Вы написали: $review_text',
        ),
    )
)
async def review_text(ctx: GeneralReviewContext) -> str:
    return ctx.review_text


def register_review_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
