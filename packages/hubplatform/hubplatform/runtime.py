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

from packaging.version import Version


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
    protocol: int
    """Protocol version of the launcher that started the app."""
    releases_dir: Path
    runtimes_dir: Path
    envs_dir: Path
    release: Version
    """Version of the release the launcher started."""
    runtime: str
    """Id of the runtime the release runs on."""
    health_file: Path
    """File the app creates once it started (see :func:`signal_healthy`)."""

    ENV_PROTOCOL = 'HUBPLATFORM_LAUNCHER_PROTOCOL'
    ENV_RELEASES_DIR = 'HUBPLATFORM_RELEASES_DIR'
    ENV_RUNTIMES_DIR = 'HUBPLATFORM_RUNTIMES_DIR'
    ENV_ENVS_DIR = 'HUBPLATFORM_ENVS_DIR'
    ENV_RELEASE = 'HUBPLATFORM_RELEASE'
    ENV_RUNTIME = 'HUBPLATFORM_RUNTIME'
    ENV_HEALTH_FILE = 'HUBPLATFORM_HEALTH_FILE'

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LauncherEnvironment | None:
        """Read the environment set by the launcher.

        :return: ``None`` if the app was not started by a launcher.
        :raises ValueError: the launcher set an invalid environment.
        """
        env = env if env is not None else dict(os.environ)
        if cls.ENV_PROTOCOL not in env:
            return None

        return cls(
            protocol=int(env[cls.ENV_PROTOCOL]),
            releases_dir=Path(env[cls.ENV_RELEASES_DIR]),
            runtimes_dir=Path(env[cls.ENV_RUNTIMES_DIR]),
            envs_dir=Path(env[cls.ENV_ENVS_DIR]),
            release=Version(env[cls.ENV_RELEASE]),
            runtime=env[cls.ENV_RUNTIME],
            health_file=Path(env[cls.ENV_HEALTH_FILE]),
        )


@cache
def launcher_environment() -> LauncherEnvironment | None:
    """Environment of the launcher that started the app, ``None`` if started directly."""
    return LauncherEnvironment.from_env()


def signal_healthy() -> None:
    """Tell the launcher the app started successfully.

    After an update the launcher waits for this signal; if the new release exits or hangs
    before sending it, the launcher rolls back to the previous release.
    Does nothing if the app was not started by a launcher.
    """
    env = launcher_environment()
    if env is None:
        return
    env.health_file.parent.mkdir(parents=True, exist_ok=True)
    env.health_file.touch()
