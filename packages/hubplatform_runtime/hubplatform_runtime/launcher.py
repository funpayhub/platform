from __future__ import annotations

from .env import environment
from .exitcodes import ExitCodes


ENV = environment()


def launch() -> int:
    while True:
        result = 0

        if result == 0 or result not in ExitCodes:
            return result
