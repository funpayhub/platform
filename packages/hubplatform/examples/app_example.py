from __future__ import annotations

import os
import sys
import asyncio

from pyconfigtree import Properties
from aiogram.types import Message
from aiogram.filters import Command
from hubplatform.app import HubPlatformApp
from hubplatform.i18n import global_translator
from hubplatform.app.app import AppState
from hubplatform.telegram.ui import UIManager, MenuContext
from hubplatform.logging.style import setup_logging
from hubplatform.app.components.telegram import TelegramComponent
from hubplatform.app.components.telegram.menu_ids import MenuIDs
from hubplatform.app.components.telegram.properties.builders import NodeMenuContext
from hubplatform.app.components.telegram.expressions.builders import ExpressionsListMenuContext


props = Properties(node_id='root')

telegram_component = TelegramComponent(token=os.environ['HUBPLATFORM_TELEGRAM_TOKEN'])

app = HubPlatformApp(
    version='1.0.0',
    properties=props,
    translator=global_translator(),
    components=[telegram_component],
)
setup_logging(translator=app.translator)


# Add some commands to telegram component
@telegram_component.dispatcher.message(Command('props'))
async def send_props_menu(message: Message, ui_manager: UIManager):
    await ui_manager.open_menu(
        menu_id=MenuIDs.properties.properties_menu,
        context=NodeMenuContext(node_path=[]),
        environment=message,
    )


@telegram_component.dispatcher.message(Command('sources'))
async def send_sources_list_menu(message: Message, ui_manager: UIManager):
    await ui_manager.open_menu(
        menu_id=MenuIDs.goods_sources.sources_list_menu,
        context=MenuContext(),
        environment=message,
    )


@telegram_component.dispatcher.message(Command('expressions'))
async def send_expressions_menu(message: Message, ui_manager: UIManager):
    await ui_manager.open_menu(
        menu_id=MenuIDs.expressions.expressions_list_menu,
        context=ExpressionsListMenuContext(),
        environment=message,
    )


async def main():
    if app.state is not AppState.READY:
        await app.setup()

    sys.exit(await app.run())


if __name__ == '__main__':
    asyncio.run(main())
