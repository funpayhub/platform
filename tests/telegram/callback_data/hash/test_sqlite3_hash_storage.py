from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Generator

import pytest

from hubplatform.telegram.callback_data.hash import QueryHash, Sqlite3HashStorage


@pytest.fixture
def limited_storage(db_path: Path) -> Generator[Sqlite3HashStorage, None, None]:
    storage = Sqlite3HashStorage(db_path, max_entries=2)
    storage.setup()
    yield storage
    storage.close()


def test_db_creation(storage: Sqlite3HashStorage, db_path: Path) -> None:
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


def test_db_saves(storage: Sqlite3HashStorage) -> None:
    hash_obj = QueryHash(hash='hash', query='query')
    storage.save_queries(hash_obj)

    hash_from_db = storage.get_query(hash_obj.hash)

    assert hash_from_db == hash_obj


def test_db_overrides_ts(storage: Sqlite3HashStorage) -> None:
    hash_obj = QueryHash(hash='hash', query='query')
    storage.save_queries(hash_obj)

    hash_obj._ts += 30
    storage.save_queries(hash_obj)

    hash_from_db = storage.get_query(hash_obj.hash, update_ts=False)
    assert hash_from_db.ts == hash_obj.ts


def test_truncate_removes_stale_entries(storage: Sqlite3HashStorage) -> None:
    stale_hash = QueryHash(hash='stale', query='stale query', ts=1)
    fresh_hash = QueryHash(hash='fresh', query='fresh query')
    storage.save_queries(
        stale_hash,
        fresh_hash,
        truncate_stale=False,
        truncate_excess=False,
    )

    storage.truncate(stale=True, excess=False)

    assert storage.get_query(stale_hash.hash, update_ts=False) is None
    assert storage.get_query(fresh_hash.hash, update_ts=False) == fresh_hash


def test_truncate_removes_excess_entries(limited_storage: Sqlite3HashStorage) -> None:
    hashes = [
        QueryHash(hash='oldest', query='oldest query', ts=1),
        QueryHash(hash='middle', query='middle query', ts=2),
        QueryHash(hash='newest', query='newest query', ts=3),
    ]
    limited_storage.save_queries(
        *hashes,
        truncate_stale=False,
        truncate_excess=False,
    )

    limited_storage.truncate(stale=False, excess=True)

    assert limited_storage.get_query(hashes[0].hash, update_ts=False) is None
    assert limited_storage.get_query(hashes[1].hash, update_ts=False) == hashes[1]
    assert limited_storage.get_query(hashes[2].hash, update_ts=False) == hashes[2]


# def test_save_queries_truncates_stale_entries(storage: Sqlite3HashStorage) -> None:
#     stale_hash = QueryHash(hash='stale', query='stale query', ts=1)
#     storage.save_queries(stale_hash, truncate_stale=False)
#
#     fresh_hash = QueryHash(hash='fresh', query='fresh query')
#     storage.save_queries(fresh_hash)
#
#     assert storage.get_query(stale_hash.hash, update_ts=False) is None
#     assert storage.get_query(fresh_hash.hash, update_ts=False) == fresh_hash
#
# Truncate logic has been changed: storage truncates only if amount of entries is above max.

def test_save_queries_truncates_excess_entries(
    limited_storage: Sqlite3HashStorage,
) -> None:
    hashes = [
        QueryHash(hash='oldest', query='oldest query', ts=1),
        QueryHash(hash='middle', query='middle query', ts=2),
        QueryHash(hash='newest', query='newest query', ts=3),
    ]

    limited_storage.save_queries(*hashes, truncate_stale=False)

    assert limited_storage.get_query(hashes[0].hash, update_ts=False) is None
    assert limited_storage.get_query(hashes[1].hash, update_ts=False) == hashes[1]
    assert limited_storage.get_query(hashes[2].hash, update_ts=False) == hashes[2]
