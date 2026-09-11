from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Environment:
    RELEASES_DIR: Path = Path(os.environ.get('HUBPLATFORM_RELEASES_DIR', Path.cwd() / 'releases'))
    LOGS_DIR: Path = Path(os.environ.get('HUBPLATFORM_LOGS_DIR', Path.cwd() / 'logs'))
    STORAGE_DIR: Path = Path(os.environ.get('HUBPLATFORM_STORAGE_DIR', Path.cwd() / 'storage'))
    CONFIGS_DIR: Path = Path(os.environ.get('HUBPLATFORM_CONFIGS_DIR', Path.cwd() / 'config'))
    PLUGINS_DIR: Path = Path(os.environ.get('HUBPLATFORM_CONFIGS_DIR', Path.cwd() / 'plugins'))
    PLUGINS_ENV_DIR: Path = Path(
        os.environ.get('HUBPLATFORM_CONFIGS_DIR', Path.cwd() / 'plugins' / 'venv')
    )
