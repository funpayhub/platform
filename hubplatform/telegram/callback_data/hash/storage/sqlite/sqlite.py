from __future__ import annotations

import sqlite3
from typing import Any
from pathlib import Path
from collections.abc import Iterable, Sequence
from importlib.resources import files

from hubplatform.telegram.callback_data.hash.types import QueryHash
from hubplatform.telegram.callback_data.hash.storage.base import HashStorage


class Sqlite3HashStorage(HashStorage):
    def __init__(
        self,
        path: Path | str = 'storage/tg_query_hashes.sqlite3',
        stale_after: int = 259200,
        max_entries: int = 100000,
    ) -> None:
        self._path = Path(path)
        self._stale_after = stale_after
        self._max_entries = max_entries

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._ready = False

    def execute(
        self,
        query: str,
        params: Sequence[Any] = (),
        commit: bool = False,
        cursor: sqlite3.Cursor | None = None
    ) -> None:
        if not self._ready:
            raise RuntimeError('...')

        cursor = cursor if cursor is not None else self._conn.cursor()
        cursor.execute(query, params)
        if commit:
            self._conn.commit()


    def executemany(
        self,
        query: str,
        params: Iterable[Sequence[Any]],
        commit: bool = False,
        cursor: sqlite3.Cursor | None = None
    ) -> None:
        if not self._ready:
            raise RuntimeError('...')

        cursor = cursor if cursor is not None else self._conn.cursor()
        cursor.executemany(query, params)
        if commit:
            self._conn.commit()

    def setup(self) -> None:
        if self._ready:
            return

        if __package__:
            script = files(__package__).joinpath('schema.sql').read_text(encoding='utf-8')
        else:
            script = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')

        with self._conn:
            self._conn.executescript(script)

        self._ready = True

    def get_query(self, hash: str, update_ts: bool = True) -> QueryHash | None:
        if update_ts:
            query = """
                    UPDATE hashes
                    SET ts = UNIXEPOCH()
                    WHERE hash = ?
                    RETURNING hash, query, ts;
                    """
        else:
            query = """
                    SELECT hash, query, ts
                    FROM hashes 
                    WHERE hash = ?
                    """

        cursor = self._conn.cursor()
        self.execute(query, (hash,), cursor=cursor)
        row = cursor.fetchone()

        if update_ts:
            self._conn.commit()

        return QueryHash(hash=row[0], query=row[1], ts=row[2]) if row else None

    def save_queries(
        self,
        *hashes: QueryHash,
        truncate_stale: bool = True,
        truncate_excess: bool = True,
    ) -> None:
        with self._conn:
            self.executemany(
                """
                INSERT 
                INTO hashes(hash, query, ts)
                VALUES (?, ?, ?) ON CONFLICT(hash) DO
                UPDATE SET query = excluded.query, ts = ?;
                """,
                ((i.hash, i.query, i.ts, i.ts) for i in hashes),
            )

            cursor = self._conn.cursor()
            self.execute(
                "SELECT COUNT(*) FROM hashes", cursor=cursor
            )
            count = cursor.fetchone()[0]

            if count > self._max_entries:
                if truncate_stale:
                    self._truncate_stale()

                if truncate_excess:
                    self._truncate_excess()

    def _truncate_stale(self) -> None:
        self.execute(
            """
            DELETE
            FROM hashes
            WHERE ts <= UNIXEPOCH() - ?;
            """,
            (self.stale_after,),
        )

    def _truncate_excess(self) -> None:
        self.execute(
            """
            DELETE
            FROM hashes
            WHERE rowid IN (SELECT rowid
                            FROM hashes
                            ORDER BY ts DESC, rowid DESC
                            LIMIT -1 OFFSET ?);
            """,
            (int(self.max_entries * 1.2),),
        )

    def truncate(self, stale: bool = True, excess: bool = True) -> None:
        if not stale and not excess:
            return

        with self._conn:
            if stale:
                self._truncate_stale()
            if excess:
                self._truncate_excess()

    def close(self) -> None:
        self._conn.close()
        self._ready = False

    @property
    def stale_after(self) -> int:
        return self._stale_after

    @property
    def max_entries(self) -> int:
        return self._max_entries
