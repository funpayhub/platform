from __future__ import annotations


__all__ = ['register_message_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.traits import TraitsContainer
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression

from .traits import MessageTrait
from ...expressions.manager.category import ExpressionsCategoryInfo


CATEGORY = ('general', 'message')

_manager = ExpressionsManager({})
_manager.add_trait(MessageTrait, 'message')
_manager.add_category(
    CATEGORY,
    ExpressionsCategoryInfo(
        name=I18nString(
            'hubplatform.expressions.general:message:name',
            'Сообщение',
        ),
        description=I18nString(
            'hubplatform.expressions.general:message:description',
            'Данные сообщения, которое отправил пользователь.',
        ),
    ),
)


@_manager.register(call_key='message_id', category=CATEGORY)
@expression(
    requires=MessageTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:message.message_id:name',
            'ID сообщения',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:message.message_id:description',
            'Идентификатор сообщения на маркетплейсе. Пример: $message_id',
        ),
    ),
)
async def message_id(traits: TraitsContainer) -> str:
    return traits[MessageTrait].message_id


@_manager.register(call_key='message_text', category=CATEGORY)
@expression(
    requires=MessageTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:message.message_text:name',
            'Текст сообщения',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:message.message_text:description',
            'Текст сообщения пользователя. Пример: Вы написали: $message_text',
        ),
    ),
)
async def message_text(traits: TraitsContainer) -> str:
    return traits[MessageTrait].message_text


def register_message_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
