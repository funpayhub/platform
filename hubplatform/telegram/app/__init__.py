from __future__ import annotations


__all__ = [
    'TELEGRAM_APP_ROUTER',
    'TELEGRAM_APP_UI_REGISTRY',
]


from hubplatform.telegram.ui import UIRegistry
from hubplatform.telegram.router import Router

from .ui.router import ui_router
from .ui.builders import basic_ui_registry
from .properties.router import props_router
from .properties.builders import properties_ui_registry
from .expressions.builders import expressions_ui_registry


TELEGRAM_APP_ROUTER = Router(name='hubplatform.telegram_app')
TELEGRAM_APP_ROUTER.include_routers(
    props_router,
    ui_router,
)

TELEGRAM_APP_UI_REGISTRY = UIRegistry()
TELEGRAM_APP_UI_REGISTRY.merge_from(
    properties_ui_registry, expressions_ui_registry, basic_ui_registry
)
