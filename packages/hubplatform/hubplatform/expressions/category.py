from __future__ import annotations


__all__ = [
    'ExpressionsCategory',
    'dummy_category',
]

from dataclasses import dataclass

from hubplatform.i18n import I18nString


@dataclass(frozen=True)
class ExpressionsCategory:
    name: str
    description: str


def dummy_category() -> ExpressionsCategory:
    return ExpressionsCategory(
        name=I18nString('hubplatform.expressions_category.dummy.name'),
        description=I18nString('hubplatform.expressions_category.dummy.description'),
    )
