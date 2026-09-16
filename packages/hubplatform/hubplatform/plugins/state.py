from __future__ import annotations


__all__ = [
    'JsonPluginStateStore',
    'MemoryPluginStateStore',
    'PluginStateStore',
]


import os
import json
import tempfile
from typing import Any
from abc import ABC, abstractmethod
from pathlib import Path
from collections.abc import Mapping

from packaging.version import Version

from .types import PluginRecord
from .exceptions import PluginStateError


class PluginStateStore(ABC):
    """Persistence port for the desired plugin inventory."""

    @abstractmethod
    def load(self) -> dict[str, PluginRecord]:
        pass

    @abstractmethod
    def save(self, records: Mapping[str, PluginRecord]) -> None:
        pass


class MemoryPluginStateStore(PluginStateStore):
    def __init__(self, records: Mapping[str, PluginRecord] | None = None) -> None:
        self._records = dict(records or {})

    def load(self) -> dict[str, PluginRecord]:
        return self._records.copy()

    def save(self, records: Mapping[str, PluginRecord]) -> None:
        self._records = dict(records)


class JsonPluginStateStore(PluginStateStore):
    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, PluginRecord]:
        if not self._path.exists():
            return {}

        try:
            parsed: Any = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(parsed, dict):
                raise TypeError('Plugin state root must be an object.')
            if parsed.get('schema_version') != self.SCHEMA_VERSION:
                raise ValueError('Unsupported plugin state schema version.')

            plugins = parsed.get('plugins')
            if not isinstance(plugins, list):
                raise TypeError('Plugin state field "plugins" must be a list.')

            records: dict[str, PluginRecord] = {}
            for raw_record in plugins:
                record = self._parse_record(raw_record)
                if record.plugin_id in records:
                    raise ValueError(f'Duplicate plugin state for {record.plugin_id!r}.')
                records[record.plugin_id] = record
            return records
        except PluginStateError:
            raise
        except Exception as exc:
            raise PluginStateError(f'Cannot read plugin state from {str(self._path)!r}.') from exc

    def save(self, records: Mapping[str, PluginRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'schema_version': self.SCHEMA_VERSION,
            'plugins': [
                self._serialize_record(records[plugin_id]) for plugin_id in sorted(records)
            ],
        }

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=self._path.parent,
                prefix=f'.{self._path.name}.',
                suffix='.tmp',
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._path)
        except Exception as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise PluginStateError(f'Cannot write plugin state to {str(self._path)!r}.') from exc

    @staticmethod
    def _parse_record(value: object) -> PluginRecord:
        if not isinstance(value, dict):
            raise TypeError('Plugin state entry must be an object.')

        def required_string(key: str) -> str:
            raw_value = value.get(key)
            if not isinstance(raw_value, str) or not raw_value:
                raise TypeError(f'Plugin state field {key!r} must be a non-empty string.')
            return raw_value

        def optional_string(key: str) -> str | None:
            raw_value = value.get(key)
            if raw_value is not None and not isinstance(raw_value, str):
                raise TypeError(f'Plugin state field {key!r} must be a string or null.')
            return raw_value

        def boolean(key: str, default: bool) -> bool:
            raw_value = value.get(key, default)
            if not isinstance(raw_value, bool):
                raise TypeError(f'Plugin state field {key!r} must be a boolean.')
            return raw_value

        return PluginRecord(
            plugin_id=required_string('plugin_id'),
            plugin_version=Version(required_string('plugin_version')),
            path=Path(required_string('path')),
            enabled=boolean('enabled', True),
            pending_restart=boolean('pending_restart', False),
            pending_removal=boolean('pending_removal', False),
            source=optional_string('source'),
            sha256=optional_string('sha256'),
        )

    @staticmethod
    def _serialize_record(record: PluginRecord) -> dict[str, object]:
        return {
            'plugin_id': record.plugin_id,
            'plugin_version': str(record.plugin_version),
            'path': str(record.path),
            'enabled': record.enabled,
            'pending_restart': record.pending_restart,
            'pending_removal': record.pending_removal,
            'source': record.source,
            'sha256': record.sha256,
        }
