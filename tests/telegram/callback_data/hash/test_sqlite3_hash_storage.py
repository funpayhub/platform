from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from hubplatform.telegram.callback_data.hash import QueryHash, Sqlite3HashStorage


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / 'tmp_path'


@pytest_asyncio.fixture
async def storage(db_path: Path) -> AsyncGenerator[Sqlite3HashStorage, None]:
    storage = Sqlite3HashStorage(db_path)
    await storage.setup()
    yield storage
    storage._conn.close()


@pytest.mark.asyncio
async def test_db_creation(storage: Sqlite3HashStorage, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT name, type
        FROM pragma_table_info('hashes')
        """
    )
    assert cursor.fetchall() == [
        ('hash', 'TEXT'),
        ('query', 'TEXT'),
        ('ts', 'INTEGER'),
    ]

    conn.close()


@pytest.mark.asyncio
async def test_db_saves(storage: Sqlite3HashStorage) -> None:
    hash_obj = QueryHash(hash='hash', query='query')
    await storage.save_queries(hash_obj)

    hash_from_db = await storage.get_query(hash_obj.hash)

    assert hash_from_db == hash_obj


@pytest.mark.asyncio
async def test_db_overrides_ts(storage: Sqlite3HashStorage) -> None:
    hash_obj = QueryHash(hash='hash', query='query')
    await storage.save_queries(hash_obj)

    hash_obj._ts += 30
    await storage.save_queries(hash_obj)

    hash_from_db = await storage.get_query(hash_obj.hash, update_ts=False)
    assert hash_from_db.ts == hash_obj.ts
