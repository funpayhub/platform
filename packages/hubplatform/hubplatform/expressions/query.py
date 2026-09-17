from __future__ import annotations


__all__ = [
    'CategoriesQuery',
    'InCategory',
    'CategoriesAndQuery',
    'CategoriesOrQuery',
    'CategoriesNotQuery',
    'CategoriesQueryParser',
]

from typing import TYPE_CHECKING, NoReturn, final
from abc import ABC, abstractmethod


if TYPE_CHECKING:
    from .registry import ExpressionsRegistry


class CategoriesQuery(ABC):
    _precedence: int

    def __and__(self, other: CategoriesQuery) -> CategoriesAndQuery:
        if not isinstance(other, CategoriesQuery):
            raise TypeError('CategoriesQuery can only be combined with other `CategoriesQuery`.')
        return CategoriesAndQuery(self, other)

    def __or__(self, other: CategoriesQuery) -> CategoriesOrQuery:
        if not isinstance(other, CategoriesQuery):
            raise TypeError('CategoriesQuery can only be combined with other `CategoriesQuery`')
        return CategoriesOrQuery(self, other)

    def __invert__(self) -> CategoriesNotQuery:
        return CategoriesNotQuery(self)

    @abstractmethod
    def __call__(self, expression_id: str, registry: ExpressionsRegistry) -> bool: ...

    @abstractmethod
    def _to_str(self, parent_precedence: int = 0) -> str: ...

    def __str__(self) -> str:
        return self._to_str()


@final
class InCategory(CategoriesQuery):
    _precedence = 1000

    def __init__(self, category_id: str) -> None:
        self.category_id = category_id

    def __call__(self, expression_id: str, registry: ExpressionsRegistry) -> bool:
        return expression_id in registry.get_expressions(self.category_id)

    def _to_str(self, parent_precedence: int = 0) -> str:
        return self.category_id


def _convert_query(query: CategoriesQuery | str) -> CategoriesQuery:
    if isinstance(query, CategoriesQuery):
        return query
    if isinstance(query, str):
        return InCategory(query)
    raise TypeError('Query can only be a category ID (str) or CategoriesQuery.')


@final
class CategoriesAndQuery(CategoriesQuery):
    _precedence = 200

    def __init__(self, *queries: CategoriesQuery | str) -> None:
        self.queries: list[CategoriesQuery] = []
        for i in queries:
            self.queries.append(_convert_query(i))

    def __call__(self, expression_id: str, registry: ExpressionsRegistry) -> bool:
        return all(query(expression_id, registry) for query in self.queries)

    def _to_str(self, parent_precedence: int = 0) -> str:
        result = '&'.join(query._to_str(self._precedence) for query in self.queries)
        return f'({result})' if self._precedence < parent_precedence else result


@final
class CategoriesOrQuery(CategoriesQuery):
    _precedence = 100

    def __init__(self, *queries: CategoriesQuery | str) -> None:
        self.queries: list[CategoriesQuery] = []
        for i in queries:
            self.queries.append(_convert_query(i))

    def __call__(self, expression_id: str, registry: ExpressionsRegistry) -> bool:
        return any(query(expression_id, registry) for query in self.queries)

    def _to_str(self, parent_precedence: int = 0) -> str:
        result = '|'.join(query._to_str(self._precedence) for query in self.queries)
        return f'({result})' if self._precedence < parent_precedence else result


@final
class CategoriesNotQuery(CategoriesQuery):
    _precedence = 300

    def __init__(self, query: CategoriesQuery | str) -> None:
        self.query = _convert_query(query)

    def __call__(self, expression_id: str, registry: ExpressionsRegistry) -> bool:
        return not self.query(expression_id, registry)

    def _to_str(self, parent_precedence: int = 0) -> str:
        result = f'~{self.query._to_str(self._precedence)}'
        return f'({result})' if self._precedence < parent_precedence else result


class CategoriesQueryParseError(ValueError):
    pass


class CategoriesQueryParser:
    _RESERVED_CHARACTERS = frozenset('~&|()')

    @classmethod
    def parse(cls, source: str) -> CategoriesQuery:
        if not source.strip():
            cls._raise_error(source, 0, 'Expected a category query')

        query, pos = cls._parse_or(source, 0)
        pos = cls._skip_whitespace(source, pos)

        if pos < len(source):
            cls._raise_error(source, pos, f'Unexpected character {source[pos]!r}')
        return query

    @classmethod
    def _parse_or(cls, source: str, pos: int) -> tuple[CategoriesQuery, int]:
        query, pos = cls._parse_and(source, pos)

        while True:
            consumed, pos = cls._consume(source, pos, '|')

            if not consumed:
                return query, pos

            right, pos = cls._parse_and(source, pos)
            query = CategoriesOrQuery(query, right)

    @classmethod
    def _parse_and(cls, source: str, pos: int) -> tuple[CategoriesQuery, int]:
        query, pos = cls._parse_unary(source, pos)

        while True:
            consumed, pos = cls._consume(source, pos, '&')

            if not consumed:
                return query, pos

            right, pos = cls._parse_unary(source, pos)
            query = CategoriesAndQuery(query, right)

    @classmethod
    def _parse_unary(cls, source: str, pos: int) -> tuple[CategoriesQuery, int]:
        consumed, pos = cls._consume(source, pos, '~')

        if consumed:
            query, pos = cls._parse_unary(source, pos)
            return CategoriesNotQuery(query), pos

        return cls._parse_primary(source, pos)

    @classmethod
    def _parse_primary(cls, source: str, pos: int) -> tuple[CategoriesQuery, int]:
        consumed, pos = cls._consume(source, pos, '(')

        if not consumed:
            return cls._parse_category(source, pos)

        query, pos = cls._parse_or(source, pos)
        consumed, pos = cls._consume(source, pos, ')')

        if not consumed:
            cls._raise_error(source, pos, 'Expected closing parenthesis')

        return query, pos

    @classmethod
    def _parse_category(cls, source: str, pos: int) -> tuple[InCategory, int]:
        pos = cls._skip_whitespace(source, pos)
        start = pos
        source_length = len(source)

        while pos < source_length:
            character = source[pos]

            if character.isspace() or character in cls._RESERVED_CHARACTERS:
                break

            pos += 1

        if pos == start:
            cls._raise_error(source, pos, 'Expected a category ID')

        return InCategory(source[start:pos]), pos

    @staticmethod
    def _consume(source: str, pos: int, expected: str) -> tuple[bool, int]:
        pos = CategoriesQueryParser._skip_whitespace(source, pos)

        if pos < len(source) and source[pos] == expected:
            return True, pos + 1

        return False, pos

    @staticmethod
    def _skip_whitespace(source: str, pos: int) -> int:
        source_length = len(source)

        while pos < source_length and source[pos].isspace():
            pos += 1

        return pos

    @staticmethod
    def _raise_error(source: str, pos: int, message: str) -> NoReturn:
        pointer = ' ' * pos + '^'

        raise CategoriesQueryParseError(f'{message} at position {pos}:\n{source}\n{pointer}')
