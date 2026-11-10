from __future__ import annotations

from typing import Sequence, Container, Generator
from dataclasses import dataclass


type CategoryPath = tuple[str, ...]


@dataclass(frozen=True)
class ExpressionsCategoryInfo:
    name: str
    description: str


class ExpressionsCategoryNode:
    def __init__(
        self,
        category_id: str | None = None,
        info: ExpressionsCategoryInfo | None = None,
    ) -> None:
        self._id = category_id
        self._info = info
        self._path: CategoryPath = () if category_id is None else (category_id,)
        self._parent: ExpressionsCategoryNode | None = None
        self._subcategories: dict[str, ExpressionsCategoryNode] = {}

    def _add_subcategory(self, subcategory: ExpressionsCategoryNode) -> None:
        assert subcategory._id is not None
        self._subcategories[subcategory._id] = subcategory
        subcategory._parent = self
        subcategory._path = (*self._path, subcategory._id)

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def path(self) -> CategoryPath:
        return self._path

    @property
    def info(self) -> ExpressionsCategoryInfo | None:
        return self._info

    @property
    def parent(self) -> ExpressionsCategoryNode | None:
        return self._parent

    @property
    def subcategories(self) -> dict[str, ExpressionsCategoryNode]:
        return self._subcategories.copy()

    @property
    def is_root(self) -> bool:
        return self._parent is None

    @property
    def chain_to_root(self) -> Generator[ExpressionsCategoryNode, None, None]:
        curr: ExpressionsCategoryNode | None = self
        while curr is not None:
            yield curr
            curr = curr._parent

    @property
    def chain_to_tails(self) -> Generator[ExpressionsCategoryNode, None, None]:
        yield self
        for subcategory in self._subcategories.values():
            yield from subcategory.chain_to_tails

    def subcategory_chains(
        self, populated: Container[CategoryPath | None]
    ) -> list[list[ExpressionsCategoryNode]]:
        """Subcategories that have expressions in them, each as a chain of categories.

        A chain starts with a direct subcategory. While the last category of a chain has no
        expressions of its own and exactly one subcategory with expressions in it, that
        subcategory is appended to the chain. Subcategories without expressions are skipped.

        :param populated: Paths of the categories that have expressions of their own, e.g. the
            keys of `ExpressionsScope.scope_expressions_by_category`.
        """

        def has_expressions(node: ExpressionsCategoryNode) -> bool:
            return any(i._path in populated for i in node.chain_to_tails)

        chains = []
        for subcategory in self._subcategories.values():
            if not has_expressions(subcategory):
                continue

            chain = [subcategory]
            while chain[-1]._path not in populated:
                non_empty = [i for i in chain[-1]._subcategories.values() if has_expressions(i)]
                if len(non_empty) != 1:
                    break
                chain.append(non_empty[0])
            chains.append(chain)
        return chains


def normalize_category_path(path: Sequence[str] | str) -> CategoryPath:
    """Validates a non-empty category path and turns it into a tuple."""
    if isinstance(path, str):
        result: tuple[str, ...] = (path,)
    else:
        result = tuple(path)

    if not result:
        raise ValueError('Category path must not be empty.')
    for index, category_id in enumerate(result):
        if not isinstance(category_id, str) or not category_id:
            raise ValueError(
                f'Invalid category ID at {index} in path {result!r}. '
                f'ID must be a non-empty string.'
            )
    return result
