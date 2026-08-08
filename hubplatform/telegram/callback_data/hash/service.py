from __future__ import annotations

import hashlib
from types import MappingProxyType
from collections.abc import Mapping

from hubplatform.exceptions import BadHashError

from . import QueryHash
from .storage import HashStorage, Sqlite3HashStorage


class HashService:
    _HASH_SYMBOLS = frozenset('0123456789abcdef')

    def __init__(self, storage: HashStorage | None = None) -> None:
        self._cache: dict[str, QueryHash] = {}
        self._storage = storage or Sqlite3HashStorage()

    @property
    def cache(self) -> Mapping[str, QueryHash]:
        return MappingProxyType(self._cache)

    @property
    def storage(self) -> HashStorage:
        return self._storage

    def _md5(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def hash(self, text: str, save: bool = False, cache: bool = True) -> str:
        if len(text) <= 64 and text.isascii():
            return text
        candidate = self._md5(text)

        query_obj: QueryHash
        while True:
            query = self.cache.get(candidate)
            if query is None:
                query = self.storage.get_query(candidate, update_ts=False)

            if query is None or query.query == text:
                query_obj = QueryHash(candidate, text)
                if cache:
                    self._cache[candidate] = query_obj
                break
            candidate = self._md5(candidate)

        if save:
            self.storage.save_queries(query_obj)
            self._cache.pop(query_obj.hash, None)

        return f'[[{candidate}]]'

    def unhash(self, hash: str) -> QueryHash:
        if not self.is_hash(hash):
            raise BadHashError(hash)

        real_hash = hash[2:-2]
        result = self.cache.get(real_hash, None) or self.storage.get_query(real_hash)
        if result is None:
            raise BadHashError(hash)
        return result

    def save(self) -> None:
        if not self.cache:
            return

        self.storage.save_queries(*self.cache.values())
        self.flush()

    def flush(self) -> None:
        self._cache.clear()

    @classmethod
    def is_hash(cls, value: str) -> bool:
        return (
            len(value) == 36 and
            value.startswith('[[') and
            value.endswith(']]') and
            all(c in cls._HASH_SYMBOLS for c in value[2:-2])
        )

    @classmethod
    def clear_hash(cls, value: str) -> str:
        if not cls.is_hash(value):
            raise BadHashError(value)

        return value[2:-2]
