from __future__ import annotations


__all__ = [
    'Command',
    'CommandsRegistry',
    'global_commands_registry',
]

from dataclasses import dataclass
from functools import cache
from collections.abc import Generator


@dataclass
class Command:
    command: str
    description: str | None = None
    setup: bool = False


class CommandsRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def add_command(self, command: Command) -> None:
        if not isinstance(command, Command):
            raise ValueError('Command must be an instance of Command.')
        if command.command in self._commands:
            raise ValueError(f'Command {command.command!r} already exists.')
        self._commands[command.command] = command

    def create_command(
        self, command: str, setup: bool = False, description: str | None = None
    ) -> Command:
        cmd = Command(command=command, description=description, setup=setup)
        self.add_command(cmd)
        return cmd

    def commands(self, setup_only: bool = False) -> Generator[Command]:
        for command in self._commands.values():
            if not command.setup and setup_only:
                continue
            yield command


@cache
def global_commands_registry() -> CommandsRegistry:
    return CommandsRegistry()
