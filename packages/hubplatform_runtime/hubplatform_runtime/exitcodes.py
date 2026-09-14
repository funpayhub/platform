from __future__ import annotations


__all__ = ['ExitCodes']

from enum import IntEnum, unique


@unique
class ExitCodes(IntEnum):
    SHUTDOWN = 0
    RESTART = 100
    RESTART_SAFE = 101
    RESTART_NORMAL = 102
    UPDATE = 103
