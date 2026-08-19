from __future__ import annotations

from collections.abc import Sequence

from hubplatform.telegram.ui import MenuContextSnapshot
from hubplatform.telegram.callback_data import CallbackData


class NextValue(CallbackData, identifier='hubplatform.properties.next_value'):
    node_path: Sequence[str]
    open_next: MenuContextSnapshot
