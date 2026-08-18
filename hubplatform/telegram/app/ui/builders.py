from __future__ import annotations

from hubplatform.telegram.ui import UIRegistry


registry = UIRegistry()


@registry.add_menu_builder('hubplatform.properties_node')
async def build_properties_node_menu(): ...
