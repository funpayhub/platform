from __future__ import annotations


__all__ = ['AppEnvironment', 'app_environment']

import os
from dataclasses import field, dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppEnvironment:
    logs_dir: Path = field(
        init=False,
        default=Path(os.environ.get('HUBPLATFORM_LOGS_DIR', Path(os.getcwd()) / 'logs')),
    )

    file_goods_sources_dir: Path = field(
        init=False,
        default=Path(
            os.environ.get(
                'HUBPLATFORM_FILE_GOODS_SOURCES_DIR',
                Path(os.getcwd()) / 'storage' / 'goods',
            )
        ),
    )


app_environment = AppEnvironment()
