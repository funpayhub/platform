from __future__ import annotations

from pathlib import Path
from collections.abc import Generator

import pytest

from hubplatform.telegram.callback_data.hash import Sqlite3HashStorage


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / 'tmp_path'


@pytest.fixture
def storage(db_path: Path) -> Generator[Sqlite3HashStorage, None, None]:
    storage = Sqlite3HashStorage(db_path)
    storage.setup()
    yield storage
    storage.close()
