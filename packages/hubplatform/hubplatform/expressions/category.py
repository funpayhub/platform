from __future__ import annotations


__all__ = [
    'ExpressionsCategory',
    'ExpressionsCategoryNode',
    'dummy_category',
]

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping, Generator

from hubplatform.i18n import I18nString


@dataclass(frozen=True)
class ExpressionsCategory:
    name: str
    description: str


class ExpressionsCategoryNode:
    """A node of the categories tree. The root node has no ID and no category."""

    def __init__(
        self, category_id: str | None = None, category: ExpressionsCategory | None = None
    ) -> None:
        self._id = category_id
        self._category = category
        self._parent: ExpressionsCategoryNode | None = None
        self._subcategories: dict[str, ExpressionsCategoryNode] = {}
        self._subcategories_proxy = MappingProxyType(self._subcategories)

    def _add_subcategory(self, subcategory: ExpressionsCategoryNode) -> None:
        assert subcategory._id is not None
        self._subcategories[subcategory._id] = subcategory
        subcategory._parent = self

    @property
    def id(self) -> str | None:
        """Full dot-separated category ID, or `None` for the root."""
        return self._id

    @property
    def name(self) -> str | None:
        """The last part of the ID, or `None` for the root."""
        return None if self._id is None else self._id.rsplit('.', 1)[-1]

    @property
    def category(self) -> ExpressionsCategory | None:
        """The registered category, or `None` if it exists only as a part of another category's ID
        or is used by expressions without being registered."""
        return self._category

    @property
    def parent(self) -> ExpressionsCategoryNode | None:
        return self._parent

    @property
    def subcategories(self) -> Mapping[str, ExpressionsCategoryNode]:
        """Direct subcategories by their full IDs, in registration order."""
        return self._subcategories_proxy

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def chain_to_root(self) -> Generator[ExpressionsCategoryNode, None, None]:
        """This node and its ancestors, the root node included."""
        curr: ExpressionsCategoryNode | None = self
        while curr is not None:
            yield curr
            curr = curr._parent


def dummy_category() -> ExpressionsCategory:
    return ExpressionsCategory(
        name=I18nString('hubplatform.expressions_category.dummy.name'),
        description=I18nString('hubplatform.expressions_category.dummy.description'),
    )
