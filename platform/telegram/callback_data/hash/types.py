from __future__ import annotations


__all__ = [
    'QueryHash',
]


import time


class QueryHash:
    def __init__(self, hash: str, query: str, ts: int = 0) -> None:
        self._hash = hash
        self._query = query
        self._ts = ts or int(time.time())

    @property
    def hash(self) -> str:
        return self._hash

    @property
    def query(self) -> str:
        return self._query

    @property
    def ts(self) -> int:
        return self._ts

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, QueryHash):
            return False
        return self._hash == o.hash

    def __hash__(self) -> int:
        return hash(self._hash)
