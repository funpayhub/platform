"""App side of the launcher protocol.

An app is started by a launcher: a small, separately installed program that runs the current
release, restarts it and switches releases. The launcher and the app are versioned
independently (the launcher is installed once and is not updated together with the app),
so they communicate only through:

* exit codes (:class:`ExitCodes`);
* environment variables the launcher sets for the app (:class:`LauncherEnvironment`);
* files in the releases directory (see :mod:`hubplatform.updates.releases`).

Any change to them must stay compatible with launchers already installed,
or bump :data:`LAUNCHER_PROTOCOL`.
"""

from __future__ import annotations


__all__ = [
    'LAUNCHER_PROTOCOL',
    'ExitCodes',
    'LauncherEnvironment',
    'launcher_environment',
    'signal_healthy',
]

import os
from dataclasses import dataclass
from enum import IntEnum, unique
from pathlib import Path
from functools import cache


LAUNCHER_PROTOCOL = 1
"""Protocol version this app implements."""


@unique
class ExitCodes(IntEnum):
    """Exit codes the app uses to ask the launcher for an action.

    Any other code is treated as a crash.
    """

    SHUTDOWN = 0
    RESTART = 100
    """Restart in the same mode."""
    RESTART_SAFE = 101
    """Restart in safe mode."""
    RESTART_NORMAL = 102
    """Restart in normal mode."""
    UPDATE = 103
    """Switch to the staged release and start it."""


@dataclass(frozen=True)
class LauncherEnvironment:
    protocol: int = int(os.environ.get('HUBPLATFORM_LAUNCHER_PROTOCOL', 1))
    releases_dir: Path = Path(os.environ.get('HUBPLATFORM_RELEASES_DIR', Path('./releases')))
    health_file: str = str(os.environ.get('HUBPLATFORM_HEALTH_FILE', 'health_check'))


@cache
def launcher_environment() -> LauncherEnvironment:
    """Environment of the launcher that started the app, ``None`` if started directly."""
    return LauncherEnvironment()


def signal_healthy() -> None:
    """Tell the launcher the app started successfully.

    After an update the launcher waits for this signal; if the new release exits or hangs
    before sending it, the launcher rolls back to the previous release.
    Does nothing if the app was not started by a launcher.
    """
    env = launcher_environment()
    env.health_file.parent.mkdir(parents=True, exist_ok=True)
    env.health_file.touch()
