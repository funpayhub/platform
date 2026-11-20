from __future__ import annotations


__all__ = ['register_order_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.traits import TraitsContainer
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression

from .traits import OrderTrait
from ...expressions.manager.category import ExpressionsCategoryInfo


CATEGORY = ('general', 'order')

_manager = ExpressionsManager({})
_manager.add_trait(OrderTrait, 'order')
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


@_manager.register(call_key='order_id', category=CATEGORY)
@expression(
    requires=OrderTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_id:name',
            'ID заказа',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_id:description',
            'Идентификатор заказа на маркетплейсе. Пример: Ваш заказ №$order_id',
        ),
    ),
)
async def order_id(traits: TraitsContainer) -> str:
    return traits[OrderTrait].order_id


@_manager.register(call_key='order_name', category=CATEGORY)
@expression(
    requires=OrderTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_name:name',
            'Название заказа',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_name:description',
            'Название заказа: то, что купил пользователь. Пример: Вы купили $order_name',
        ),
    ),
)
async def order_name(traits: TraitsContainer) -> str:
    return traits[OrderTrait].order_name


@_manager.register(call_key='order_amount', category=CATEGORY)
@expression(
    requires=OrderTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:order.order_amount:name',
            'Количество в заказе',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:order.order_amount:description',
            'Количество единиц товара в заказе. Пример: Количество: $order_amount',
        ),
    ),
)
async def order_amount(traits: TraitsContainer) -> int:
    return traits[OrderTrait].order_amount


def register_order_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
