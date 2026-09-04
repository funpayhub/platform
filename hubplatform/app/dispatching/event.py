from __future__ import annotations

from typing import Any


__all__ = [
    'HubPlatformEvent',
    'NodeAttachedEvent',
    'NodeDetachedEvent',
    'ParameterValueChangedEvent',
]

from pyconfigtree import Node, MutableParameter
from eventry.asyncio import ExtendedEvent


class HubPlatformEvent(ExtendedEvent, event_name='__hubplatform_event__'):
    pass


class ParameterValueChangedEvent(HubPlatformEvent, event_name='hubplatform_param_value_changed'):
    def __init__(self, parameter: MutableParameter[Any]) -> None:
        super().__init__()
        self._parameter = parameter

    @property
    def parameter(self) -> MutableParameter[Any]:
        return self._parameter

    def context_injection(self) -> dict[str, Any]:
        return super().context_injection() | {'parameter': self._parameter}


class NodeAttachedEvent(HubPlatformEvent, event_name='hubplatform_node_attached'):
    def __init__(self, attached_node: Node, attached_to: Node) -> None:
        super().__init__()
        self._attached_node = attached_node
        self._attached_to = attached_to

    @property
    def attached_node(self) -> Node:
        return self._attached_node

    @property
    def attached_to(self) -> Node:
        return self._attached_to

    def context_injection(self) -> dict[str, Any]:
        return super().context_injection() | {
            'attached_node': self._attached_node,
            'attached_to': self._attached_to,
        }


class NodeDetachedEvent(HubPlatformEvent, event_name='hubplatform_node_detached'):
    def __init__(self, detached_node: Node, detached_from: Node) -> None:
        super().__init__()
        self._detached_node = detached_node
        self._detached_from = detached_from

    @property
    def detached_node(self) -> Node:
        return self._detached_node

    @property
    def detached_from(self) -> Node:
        return self._detached_from

    def context_injection(self) -> dict[str, Any]:
        return super().context_injection() | {
            'detached_node': self._detached_node,
            'detached_from': self._detached_from,
        }
