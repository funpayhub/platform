from __future__ import annotations

import sqlite3
from pathlib import Path
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

        self._conn = sqlite3.connect(str(self._path))

    async def setup(self) -> None:
        if __package__:
            script = files(__package__).joinpath('schema.sql').read_text(encoding='utf-8')
        else:
            script = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')

        with self._conn:
            self._conn.executescript(script)

    async def get_query(self, hash: str, update_ts: bool = True) -> QueryHash | None:
        if update_ts:
            query = """
                    UPDATE hashes
                    SET ts = strftime('%s', 'now')
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
        cursor.execute(query, (hash,))
        row = cursor.fetchone()

        return QueryHash(hash=row[0], query=row[1], ts=row[2]) if row else None

    async def save_queries(
        self,
        *hashes: QueryHash,
        truncate_stale: bool = True,
        truncate_excess: bool = True,
    ) -> None:
        with self._conn:
            cursor = self._conn.cursor()
            cursor.executemany(
                """
                INSERT 
                INTO hashes(hash, query, ts)
                VALUES (?, ?, ?) ON CONFLICT(hash) DO
                UPDATE SET query = excluded.query, ts = ?;
                """,
                ((i.hash, i.query, i.ts, i.ts) for i in hashes),
            )

            if truncate_stale:
                await self._truncate_stale()

            if truncate_excess:
                await self._truncate_excess()

    async def _truncate_stale(self) -> None:
        self._conn.execute(
            """
            DELETE
            FROM hashes
            WHERE ts <= UNIXEPOCH() - ?;
            """,
            (self.stale_after,),
        )

    async def _truncate_excess(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                DELETE
                FROM hashes
                WHERE rowid IN (SELECT rowid
                                FROM hashes
                                ORDER BY ts DESC, rowid DESC
                                LIMIT -1 OFFSET ?);
                """,
                (self.max_entries,),
            )

    async def truncate(self, stale: bool = True, excess: bool = True) -> None:
        if not stale and not excess:
            return

        with self._conn:
            if stale:
                await self._truncate_stale()
            if excess:
                await self._truncate_excess()

    @property
    def stale_after(self) -> int:
        return self._stale_after

    @property
    def max_entries(self) -> int:
        return self._max_entries
