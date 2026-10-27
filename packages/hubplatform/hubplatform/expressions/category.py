from __future__ import annotations


__all__ = [
    'ExpressionsCategory',
]

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressionsCategory:
    name: str
    description: str
