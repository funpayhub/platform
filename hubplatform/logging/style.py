from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, Sequence
from numbers import Number
from typing import Any, TextIO

from hubplatform.i18n import I18nString, Translator


RESET = '\x1b[0m'
BOLD = '\x1b[1m'

LEVEL_COLORS = {
    logging.DEBUG: '\x1b[2;37m',
    logging.INFO: '\x1b[1;32m',
    logging.WARNING: '\x1b[33m',
    logging.ERROR: '\x1b[31m',
    logging.CRITICAL: '\x1b[37;41m',
}
UNKNOWN_LEVEL_COLOR = ''

LEVEL_EMOJIS = {
    logging.DEBUG: '🔎',
    logging.INFO: '📘',
    logging.WARNING: '⚠️',
    logging.ERROR: '‼️',
    logging.CRITICAL: '🔥',
}
UNKNOWN_LEVEL_EMOJI = '📄'

LEVEL_NAMES = {
    logging.DEBUG: 'DBUG',
    logging.INFO: 'INFO',
    logging.WARNING: 'WARN',
    logging.ERROR: 'ERRR',
    logging.CRITICAL: 'CRIT',
}

STRING_COLOR = '\x1b[32m'
NUMBER_COLOR = '\x1b[33m'
ERROR_COLOR = '\x1b[31m'
UNKNOWN_COLOR = '\x1b[37m'
PLUGIN_COLOR = '\x1b[36m'

BRACKET_COLORS = (
    '\x1b[36m',
    '\x1b[35m',
    '\x1b[34m',
    '\x1b[33m',
    '\x1b[32m',
    '\x1b[31m',
)


RESET_RE = re.compile(r'\$\$RESET|(?<!\$)\$RESET')

ESC_RE = re.compile(
    r'''
    \x1b
    (?:
        \[[0-?]*[ -/]*[@-~]
        |
        \][^\x07\x1b]*(?:\x07|\x1b\\)
        |
        [PX^_][^\x1b]*(?:\x1b\\)
        |
        [@-_]
    )
    ''',
    re.VERBOSE,
)

PERCENT_RE = re.compile(
    r'%'
    r'(?:\((?P<mapping_key>[^)]+)\))?'
    r'(?P<flags>[#0\-+ ]*)'
    r'(?P<width>\*|\d+)?'
    r'(?P<precision>\.(?:\*|\d+))?'
    r'(?P<length>[hlL])?'
    r'(?P<conversion>[diouxXeEfFgGcrsa%])',
)


def replace_reset_markers(text: str, replacement: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group() == '$$RESET':
            return '$RESET'

        return replacement

    return RESET_RE.sub(replace, text)


def strip_control_sequences(text: str) -> str:
    text = replace_reset_markers(text, '')
    return ESC_RE.sub('', text)


def translate_message(message: object, translator: Translator | None) -> str:
    if isinstance(message, I18nString):
        return message.translate_(translator=translator)
    return str(message)


def plain_message(record: logging.LogRecord, translator: Translator | None) -> str:
    message = translate_message(record.msg, translator)
    if record.args:
        message %= record.args
    return message


class ValueRenderer:
    def render(self, v: Any, *, depth: int = 0, nested: bool = False, seen: set[int] | None = None) -> str:
        if seen is None:
            seen = set()

        if isinstance(v, Mapping):
            return self._render_mapping(v, depth=depth, seen=seen)

        if self._is_sequence(v):
            return self._render_sequence(v, depth=depth, seen=seen)

        return self._render_scalar(v, nested=nested)

    def colorize_formatted(self, text: str, value: Any) -> str:
        return self._paint(text, self._value_color(value))

    def _render_scalar(self, value: Any, *, nested: bool) -> str:
        return self.colorize_formatted(repr(value) if nested else str(value), value)

    def _render_mapping(self, value: Mapping[Any, Any], *, depth: int, seen: set[int]) -> str:
        object_id = id(value)
        if object_id in seen:
            return self._paint('...', UNKNOWN_COLOR)

        seen.add(object_id)

        try:
            items = (
                self.render(key, depth=depth + 1, nested=True, seen=seen)
                + ': '
                + self.render(item, depth=depth + 1, nested=True, seen=seen)
                for key, item in value.items()
            )

            return self._wrap('{', ', '.join(items), '}', depth)
        finally:
            seen.remove(object_id)

    def _render_sequence(self, value: Sequence[object], *, depth: int, seen: set[int]) -> str:
        object_id = id(value)
        if object_id in seen:
            return self._paint('...', UNKNOWN_COLOR)

        seen.add(object_id)

        try:
            items = [self.render(i, depth=depth + 1, nested=True, seen=seen) for i in value]

            if isinstance(value, tuple):
                if len(items) == 1:
                    body = items[0] + ','
                else:
                    body = ', '.join(items)

                return self._wrap('(', body, ')', depth)

            return self._wrap('[', ', '.join(items), ']', depth)
        finally:
            seen.remove(object_id)

    @staticmethod
    def _is_sequence(value: object) -> bool:
        return isinstance(value, Sequence) and not isinstance(
            value,
            (str, bytes, bytearray, memoryview),
        )

    @staticmethod
    def _value_color(value: object) -> str:
        if isinstance(value, BaseException):
            return ERROR_COLOR

        if isinstance(value, str):
            return STRING_COLOR

        if isinstance(value, Number):
            return NUMBER_COLOR

        return UNKNOWN_COLOR

    @staticmethod
    def _paint(text: str, color: str) -> str:
        return f'{RESET}{color}{BOLD}{text}{RESET}'

    @staticmethod
    def _wrap(opening: str, body: str, closing: str, depth: int) -> str:
        color = BRACKET_COLORS[depth % len(BRACKET_COLORS)]
        opening = f'{RESET}{color}{BOLD}{opening}{RESET}'
        closing = f'{RESET}{color}{BOLD}{closing}{RESET}'

        return opening + body + closing


class ColoredPercentFormatter:
    def __init__(self) -> None:
        self._renderer = ValueRenderer()

    def format(self, message: str, args: object) -> str:
        if not args:
            return message

        mapping_args = args if isinstance(args, Mapping) else None
        positional_args = args if isinstance(args, tuple) else (args,)

        position = 0
        output: list[str] = []
        cursor = 0
        mapping_used_as_value = False

        while True:
            percent_position = message.find('%', cursor)
            if percent_position == -1:
                output.append(message[cursor:])
                break

            output.append(message[cursor:percent_position])

            match = PERCENT_RE.match(message, percent_position)
            if match is None:
                # Вызывает такое же исключение, какое вызвал бы обычный logging.
                message % args
                raise AssertionError('Unreachable')

            cursor = match.end()
            conversion = match.group('conversion')

            if conversion == '%':
                output.append('%')
                continue

            mapping_key = match.group('mapping_key')
            star_values: list[object] = []

            if match.group('width') == '*':
                value, position = self._next_argument(
                    positional_args,
                    position,
                    mapping_args,
                    mapping_used_as_value,
                )
                star_values.append(value)

                if mapping_args is not None:
                    mapping_used_as_value = True

            if match.group('precision') == '.*':
                value, position = self._next_argument(
                    positional_args,
                    position,
                    mapping_args,
                    mapping_used_as_value,
                )
                star_values.append(value)

                if mapping_args is not None:
                    mapping_used_as_value = True

            if mapping_key is not None:
                if mapping_args is None:
                    raise TypeError('format requires a mapping')

                value = mapping_args[mapping_key]
            else:
                value, position = self._next_argument(
                    positional_args,
                    position,
                    mapping_args,
                    mapping_used_as_value,
                )

                if mapping_args is not None:
                    mapping_used_as_value = True

            positional_spec = self._positional_spec(match)

            if star_values:
                operand: object = (*star_values, value)
            else:
                operand = value

            # Сначала проверяем, что стандартное %-форматирование допустимо.
            formatted = positional_spec % operand

            if (
                isinstance(value, (Mapping, Sequence))
                and not isinstance(value, (str, bytes, bytearray, memoryview))
                and conversion in {'s', 'r', 'a'}
                and match.group('width') is None
                and match.group('precision') is None
            ):
                formatted = self._renderer.render(value)
            else:
                formatted = self._renderer.colorize_formatted(formatted, value)

            output.append(formatted)

        if mapping_args is None and position != len(positional_args):
            raise TypeError('not all arguments converted during string formatting')

        return ''.join(output)

    @staticmethod
    def _next_argument(
        positional_args: tuple[object, ...],
        position: int,
        mapping_args: Mapping[object, object] | None,
        mapping_used_as_value: bool,
    ) -> tuple[object, int]:
        if mapping_args is not None:
            if mapping_used_as_value:
                raise TypeError('not enough arguments for format string')

            return mapping_args, position

        if position >= len(positional_args):
            raise TypeError('not enough arguments for format string')

        return positional_args[position], position + 1

    @staticmethod
    def _positional_spec(match: re.Match[str]) -> str:
        return ''.join(
            (
                '%',
                match.group('flags') or '',
                match.group('width') or '',
                match.group('precision') or '',
                match.group('length') or '',
                match.group('conversion'),
            ),
        )


class BaseFormatter(logging.Formatter):
    def format_plugin_name(
        self,
        record: logging.LogRecord,
    ) -> str:
        plugin = getattr(record, 'plugin', None)
        if plugin is None:
            return ''

        return str(plugin.manifest.name)

    def append_exception(self, text: str, record: logging.LogRecord, *, color: str = '') -> str:
        if record.exc_info is not None:
            exception = self.formatException(record.exc_info)
            text += f'\n{color}{exception}{RESET if color else ""}'

        if record.stack_info:
            text += f'\n{self.formatStack(record.stack_info)}'

        return text


class ConsoleFormatter(BaseFormatter):
    def __init__(
        self,
        translator: Translator,
        *,
        stream: TextIO = sys.stderr,
        show_logger_name: bool = False,
        force_color: bool | None = None,
    ) -> None:
        super().__init__()
        self.translator = translator
        self.stream = stream
        self.show_logger_name = show_logger_name
        self.force_color = force_color
        self._percent_formatter = ColoredPercentFormatter()

    @property
    def supports_color(self) -> bool:
        if self.force_color is not None:
            return self.force_color

        return self.stream.isatty()

    def format(self, record: logging.LogRecord) -> str:
        message = translate_message(record.msg, self.translator)

        if record.args:
            if self.supports_color:
                message = self._percent_formatter.format(
                    message,
                    record.args,
                )
            else:
                message %= record.args

        if self.supports_color:
            message = replace_reset_markers(message, RESET)
        else:
            message = strip_control_sequences(message)

        time = self.formatTime(record, '%H:%M:%S')
        level_name = LEVEL_NAMES.get(record.levelno, record.levelname)
        level_color = LEVEL_COLORS.get(
            record.levelno,
            UNKNOWN_LEVEL_COLOR,
        )

        if self.supports_color:
            time = f'\x1b[2;37m{time}{RESET}'
            level = f'{level_color}{level_name:^6}{RESET}'
            emoji = LEVEL_EMOJIS.get(
                record.levelno,
                UNKNOWN_LEVEL_EMOJI,
            )
            prefix = f'{emoji} '
        else:
            level = f'{level_name:^6}'
            prefix = ''

        logger_name = ''
        if self.show_logger_name:
            logger_name = f' [{record.name}]'

        plugin_name = self.format_plugin_name(record)
        if plugin_name:
            if self.supports_color:
                plugin_name = (
                    f' {RESET}{PLUGIN_COLOR}{BOLD}'
                    f'[{plugin_name}]{RESET}'
                )
            else:
                plugin_name = f' [{plugin_name}]'

        result = (
            f'{prefix}{time} [{level}]'
            f'{logger_name}{plugin_name} {message}'
        )

        result = self.append_exception(
            result,
            record,
            color=(
                f'{RESET}{ERROR_COLOR}{BOLD}'
                if self.supports_color
                else ''
            ),
        )

        if self.supports_color:
            result += RESET

        return result


class FileFormatter(BaseFormatter):
    def format(self, record: logging.LogRecord) -> str:
        message = plain_message(record, translator=None)

        time = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        level_name = LEVEL_NAMES.get(record.levelno, record.levelname)

        plugin_name = self.format_plugin_name(record)
        if plugin_name:
            plugin_name = f' [{plugin_name}]'

        result = (
            f'{time} [{level_name:^6}]'
            f' [{record.name}]{plugin_name} {message}'
        )

        result = self.append_exception(result, record)
        return strip_control_sequences(result)


def setup_logging(translator: Translator) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(
        ConsoleFormatter(
            translator,
            stream=console.stream,
        ),
    )

    file = logging.FileHandler('hub.log', encoding='utf-8')
    file.setLevel(logging.DEBUG)
    file.setFormatter(FileFormatter())

    root.addHandler(console)
    root.addHandler(file)
