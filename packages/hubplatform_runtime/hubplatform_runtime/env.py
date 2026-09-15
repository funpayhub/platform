from __future__ import annotations


__all__ = ['Environment', 'environment']

import os
from dataclasses import dataclass
from pathlib import Path
from functools import cache


@dataclass(frozen=True)
class Environment:
    RELEASES_DIR: Path = Path(os.environ.get('HUBPLATFORM_RELEASES_DIR', Path.cwd() / 'releases'))
    LOGS_DIR: Path = Path(os.environ.get('HUBPLATFORM_LOGS_DIR', Path.cwd() / 'logs'))
    STORAGE_DIR: Path = Path(os.environ.get('HUBPLATFORM_STORAGE_DIR', Path.cwd() / 'storage'))
    CONFIGS_DIR: Path = Path(os.environ.get('HUBPLATFORM_CONFIGS_DIR', Path.cwd() / 'config'))
    PLUGINS_DIR: Path = Path(os.environ.get('HUBPLATFORM_PLUGINS_DIR', Path.cwd() / 'plugins'))
    PLUGINS_ENV_DIR: Path = Path(
        os.environ.get('HUBPLATFORM_PLUGINS_VENV_DIR', Path.cwd() / 'plugins' / 'venv')
    )
    IS_WINDOWS = os.name == 'nt'

    def as_dict(self) -> dict[str, str]:
        return {
            'HUBPLATFORM_RELEASES_DIR': str(self.RELEASES_DIR),
            'HUBPLATFORM_LOGS_DIR': str(self.LOGS_DIR),
            'HUBPLATFORM_STORAGE_DIR': str(self.STORAGE_DIR),
            'HUBPLATFORM_CONFIGS_DIR': str(self.CONFIGS_DIR),
            'HUBPLATFORM_PLUGINS_DIR': str(self.PLUGINS_DIR),
            'HUBPLATFORM_PLUGINS_VENV_DIR': str(self.PLUGINS_ENV_DIR),
        }


@cache
def environment() -> Environment:
    return Environment()
