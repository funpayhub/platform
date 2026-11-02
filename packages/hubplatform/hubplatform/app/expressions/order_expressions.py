from __future__ import annotations


__all__ = ['register_order_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression

from .contexts import GeneralOrderContext
from ...expressions.manager.category import ExpressionsCategoryInfo


CATEGORY = ('general', 'order')

_manager = ExpressionsManager({})
_manager.add_context(GeneralOrderContext, 'general_order')
_manager.add_category(
    CATEGORY,
    ExpressionsCategoryInfo(
        name=I18nString(
            'hubplatform.expressions.general:order:name',
            'Заказ',
        ),
        description=I18nString(
            'hubplatform.expressions.general:order:description',
            'Данные заказа, с которым связано действие.',
        ),
    ),
)


@_manager.register(context_type=GeneralOrderContext, call_key='order_id', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_id:name',
            'ID заказа',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_id:description',
            'Идентификатор заказа на маркетплейсе. Пример: Ваш заказ №$order_id',
        ),
    )
)
async def order_id(ctx: GeneralOrderContext) -> str:
    return ctx.order_id


@_manager.register(context_type=GeneralOrderContext, call_key='order_name', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_name:name',
            'Название заказа',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_name:description',
            'Название заказа: то, что купил пользователь. Пример: Вы купили $order_name',
        ),
    )
)
async def order_name(ctx: GeneralOrderContext) -> str:
    return ctx.order_name


@_manager.register(context_type=GeneralOrderContext, call_key='order_amount', category=CATEGORY)
@expression(
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_amount:name',
            'Количество в заказе',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_amount:description',
            'Количество единиц товара в заказе. Пример: Количество: $order_amount',
        ),
    )
)
async def order_amount(ctx: GeneralOrderContext) -> int:
    return ctx.order_amount


def register_order_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
