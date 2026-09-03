from __future__ import annotations


__all__ = ['AppEnvironment', 'app_environment']

import os
from dataclasses import field, dataclass
from functools import cache
from pathlib import Path


_env = os.environ.get
_LOGS_DIR = Path(_env('HUBPLATFORM_LOGS_DIR', Path(os.getcwd()) / 'logs'))
_STORAGE_PATH = Path(_env('HUBPLATFORM_STORAGE_PATH', Path(os.getcwd()) / 'storage'))
_FILE_GOODS_SOURCES_DIR = Path(
    _env('HUBPLATFORM_FILE_GOODS_SOURCES_DIR',  _STORAGE_PATH / 'goods')
)



@dataclass(frozen=True)
class AppEnvironment:
    logs_dir: Path = field(default=_LOGS_DIR)
    storage_path: Path = field(default=_STORAGE_PATH)
    file_goods_sources_dir: Path = field(default=_FILE_GOODS_SOURCES_DIR)


@cache
def app_environment() -> AppEnvironment:
    return AppEnvironment()
