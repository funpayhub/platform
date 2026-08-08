from __future__ import annotations

import hashlib

from hubplatform.exceptions import BadHashError

from . import QueryHash
from .storage import HashStorage, Sqlite3HashStorage


class _HashinatorT1000:
    _HASH_SYMBOLS = frozenset('0123456789abcdef')

    def __init__(self, storage: HashStorage | None = None) -> None:
        self.hashes: dict[str, QueryHash] = {}
        self.storage = storage or Sqlite3HashStorage()

    def _md5(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def hash(self, text: str, save: bool = False, cache: bool = True) -> str:
        if len(text) <= 64 and text.isascii():
            return text
        candidate = self._md5(text)

        while True:
            query = self.hashes.get(candidate)
            if not query:
                query = self.storage.get_query(candidate, update_ts=False)

            if not query or query.query == text:
                if cache:
                    self.hashes[candidate] = QueryHash(candidate, text)
                break
            candidate = self._md5(candidate)

        if save:
            self.storage.save_queries(QueryHash(candidate, text))
            self.hashes.pop(candidate, None)

        return f'[[{candidate}]]'

    def unhash(self, hash: str) -> QueryHash:
        if not self.is_hash(hash):
            raise BadHashError(hash)

        real_hash = hash[2:-2]
        result = self.hashes.get(real_hash, None) or self.storage.get_query(real_hash)
        if result is None:
            raise BadHashError(hash)
        return result

    def save(self) -> None:
        if not self.hashes:
            return

        self.storage.save_queries(*self.hashes.values())
        self.hashes.clear()

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
