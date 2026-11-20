from __future__ import annotations


__all__ = ['register_review_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.traits import TraitsContainer
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression

from .traits import ReviewTrait
from ...expressions.manager.category import ExpressionsCategoryInfo


CATEGORY = ('general', 'review')

_manager = ExpressionsManager({})
_manager.add_trait(ReviewTrait, 'review')
_manager.add_category(
    CATEGORY,
    ExpressionsCategoryInfo(
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


@_manager.register(call_key='review_rating', category=CATEGORY)
@expression(
    requires=ReviewTrait,
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
    ),
)
async def review_rating(traits: TraitsContainer) -> int:
    return traits[ReviewTrait].review_rating


@_manager.register(call_key='review_text', category=CATEGORY)
@expression(
    requires=ReviewTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:review.review_text:name',
            'Текст отзыва',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:review.review_text:description',
            'Текст отзыва пользователя. Пример: Вы написали: $review_text',
        ),
    ),
)
async def review_text(traits: TraitsContainer) -> str:
    return traits[ReviewTrait].review_text


def register_review_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
