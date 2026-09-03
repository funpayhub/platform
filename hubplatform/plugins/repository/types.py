from __future__ import annotations


__all__ = [
    'PluginDetails',
    'PluginSummary',
    'RepositoryPage',
]


from typing import Any, Annotated

from pydantic import Field, BaseModel, ConfigDict, BeforeValidator, PlainSerializer
from packaging.version import Version


def _parse_version(value: Any) -> Version:
    if isinstance(value, Version):
        return value
    if isinstance(value, str):
        return Version(value)
    raise ValueError('Version must be a string or packaging.version.Version instance.')


RepositoryVersion = Annotated[
    Version,
    BeforeValidator(_parse_version),
    PlainSerializer(str, return_type=str, when_used='json'),
]


class _RepositoryModel(BaseModel):
    """Common model config for repository models."""
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='forbid',
        frozen=True,
    )


class PluginSummary(_RepositoryModel):
    """Represents a plugin summary."""

    plugin_id: str = Field(min_length=1)
    plugin_name: str = Field(min_length=1)
    plugin_description: str = ''
    latest_compatible_version: RepositoryVersion


class PluginDetails(_RepositoryModel):
    """Represents a plugin details."""
    plugin_id: str = Field(min_length=1)
    plugin_name: str = Field(min_length=1)
    plugin_description: str = ''
    versions: tuple[RepositoryVersion, ...] = Field(default_factory=tuple)


class RepositoryPage(_RepositoryModel):
    """Represents a page of plugins."""

    plugins: tuple[PluginSummary, ...] = Field(default_factory=tuple)
    current_cursor: str | None = None
    next_cursor: str | None = None
    total_plugins: int | None = Field(default=None, ge=0)
