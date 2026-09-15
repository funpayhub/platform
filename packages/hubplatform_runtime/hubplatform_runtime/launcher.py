from __future__ import annotations


__all__ = [
    'launch',
]

import os
import subprocess
from logging import getLogger

from .env import Environment, environment
from .args import args_parser
from .exitcodes import ExitCodes


ENV = environment()
logger = getLogger(__name__)
initial_launcher_args, initial_app_args = args_parser.parse_known_args()


def launch(env: Environment | None = None) -> int:
    env = env if env is not None else ENV
    safe = initial_launcher_args.safe

    while True:
        result = launch_current_version(env, safe)

        if result == 0 or result not in ExitCodes:
            return result

        if result == ExitCodes.RESTART_NORMAL:
            safe = False
        elif result == ExitCodes.RESTART_SAFE:
            safe = True


def launch_current_version(env: Environment, safe: bool) -> int:
    CURRENT_RELEASE_DIR = env.RELEASES_DIR / 'current'
    CURRENT_RELEASE_ENV = CURRENT_RELEASE_DIR / '.venv'

    if not CURRENT_RELEASE_DIR.is_dir():
        raise Exception(f'Current release path must be a dir ({CURRENT_RELEASE_DIR}).')

    if not CURRENT_RELEASE_ENV.is_dir():
        raise Exception(
            f'Cannot find virtual environment for current release ({CURRENT_RELEASE_ENV}).'
        )

    if env.IS_WINDOWS:
        python_executable = CURRENT_RELEASE_ENV / 'Scripts' / 'python.exe'
    else:
        python_executable = CURRENT_RELEASE_ENV / 'bin' / 'python'

    if not python_executable.is_file():
        raise Exception(
            f'Cannot find python executable for current release ({python_executable}).'
        )

    launch_args = initial_app_args
    if safe:
        launch_args = initial_app_args + ['--safe']

    return subprocess.run(
        [
            python_executable,
            CURRENT_RELEASE_DIR / 'main.py',
            *launch_args,
        ],
        cwd=CURRENT_RELEASE_DIR,
        env=os.environ | env.as_dict(),
    ).returncode
