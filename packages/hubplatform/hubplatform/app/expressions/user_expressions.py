from __future__ import annotations


__all__ = ['register_user_expressions']

from hubplatform.i18n import I18nString
from hubplatform.expressions.docs import ExpressionDocs
from hubplatform.expressions.traits import TraitsContainer
from hubplatform.expressions.manager import ExpressionsManager
from hubplatform.expressions.definition import expression

from .traits import InitiatorTrait
from ...expressions.manager.category import ExpressionsCategoryInfo


CATEGORY = ('general', 'user')

_manager = ExpressionsManager({})
_manager.add_trait(InitiatorTrait, 'initiator')
_manager.add_category(
    CATEGORY,
    ExpressionsCategoryInfo(
        name=I18nString(
            'hubplatform.expressions.general:user:name',
            'Пользователь',
        ),
        description=I18nString(
            'hubplatform.expressions.general:user:description',
            'Данные пользователя, который совершил действие.',
        ),
    ),
)


@_manager.register(call_key='username', category=CATEGORY)
@expression(
    requires=InitiatorTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:user.username:name',
            'Имя пользователя',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:user.username:description',
            'Имя пользователя на маркетплейсе, который совершил действие. '
            'Пример: Здравствуйте, $username!',
        ),
    ),
)
async def username(traits: TraitsContainer) -> str:
    return traits[InitiatorTrait].initiator_username


@_manager.register(call_key='user_id', category=CATEGORY)
@expression(
    requires=InitiatorTrait,
    docs=ExpressionDocs(
        name=I18nString(
            'hubplatform.expressions.general:user.user_id:name',
            'ID пользователя',
        ),
        overview=I18nString(
            'hubplatform.expressions.general:user.user_id:description',
            'Идентификатор на маркетплейсе пользователя, который совершил действие. '
            'Пример: $user_id',
        ),
    ),
)
async def user_id(traits: TraitsContainer) -> str:
    return traits[InitiatorTrait].initiator_id


def register_user_expressions(manager: ExpressionsManager) -> None:
    manager.merge_from(_manager, skip_existing=False)
