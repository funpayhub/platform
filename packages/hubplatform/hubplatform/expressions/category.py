from __future__ import annotations


__all__ = [
    'ExpressionsCategory',
    'DUMMY_CATEGORY',
]

from dataclasses import dataclass

from hubplatform.i18n import I18nString


@dataclass(frozen=True)
class ExpressionsCategory:
    name: str
    description: str


DUMMY_CATEGORY = ExpressionsCategory(
    name=I18nString('hubplatform.expressions_category.dummy.name'),
    description=I18nString('hubplatform.expressions_category.dummy.description'),
)
