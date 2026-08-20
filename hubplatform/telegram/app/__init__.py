from __future__ import annotations


__all__ = [
    'TELEGRAM_APP_ROUTER',
    'TELEGRAM_APP_UI_REGISTRY',
]


from hubplatform.telegram.ui import UIRegistry
from hubplatform.telegram.router import Router

from .ui.router import ui_router
from .properties.router import properties_router
from .properties.builders import properties_ui_registry


TELEGRAM_APP_ROUTER = Router(name='hubplatform.telegram_app')
TELEGRAM_APP_ROUTER.include_routers(
    properties_router,
    ui_router,
)

TELEGRAM_APP_UI_REGISTRY = UIRegistry()
TELEGRAM_APP_UI_REGISTRY.merge_from(properties_ui_registry)
