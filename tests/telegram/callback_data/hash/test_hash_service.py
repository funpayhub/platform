from __future__ import annotations

from pathlib import Path

from hubplatform.telegram.callback_data.hash.service import _HashinatorT1000
from hubplatform.telegram.callback_data.hash.storage import Sqlite3HashStorage


def test_hash_is_stable_and_persisted_across_storage_restart(tmp_path: Path) -> None:
    db_path = tmp_path / 'hashes.sqlite3'
    query = 'x' * 65

    storage = Sqlite3HashStorage(db_path)
    storage.setup()
    service = _HashinatorT1000(storage)

    query_hash = service.hash(query)
    assert service.hash(query) == query_hash

    service.save()
    storage.close()

    restored_storage = Sqlite3HashStorage(db_path)
    restored_storage.setup()
    restored_service = _HashinatorT1000(restored_storage)

    assert restored_service.unhash(query_hash).query == query

    restored_storage.close()
