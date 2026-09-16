from __future__ import annotations


__all__ = [
    'PluginAuthor',
    'PluginDependency',
    'PluginManifest',
]


from typing import Any, Literal, Annotated
from pathlib import Path

from pydantic import (
    Field,
    BaseModel,
    ConfigDict,
    BeforeValidator,
    PlainSerializer,
    field_validator,
)
from packaging.version import Version
from packaging.specifiers import SpecifierSet
from packaging.requirements import Requirement


def _parse_version(value: Any) -> Version:
    if isinstance(value, Version):
        return value
    if isinstance(value, str):
        return Version(value)
    raise TypeError('Version must be a string or packaging.version.Version instance.')


def _parse_specifier(value: Any) -> SpecifierSet:
    if isinstance(value, SpecifierSet):
        return value
    if isinstance(value, str):
        return SpecifierSet(value)
    raise TypeError('Version specifier must be a string or SpecifierSet instance.')


def _parse_requirement(value: Any) -> Requirement:
    if isinstance(value, Requirement):
        return value
    if isinstance(value, str):
        return Requirement(value)
    raise TypeError('Python dependency must be a string or Requirement instance.')


ManifestVersion = Annotated[
    Version,
    BeforeValidator(_parse_version),
    PlainSerializer(str, return_type=str, when_used='json'),
]
ManifestSpecifier = Annotated[
    SpecifierSet,
    BeforeValidator(_parse_specifier),
    PlainSerializer(str, return_type=str, when_used='json'),
]
ManifestRequirement = Annotated[
    Requirement,
    BeforeValidator(_parse_requirement),
    PlainSerializer(str, return_type=str, when_used='json'),
]


class _ManifestModel(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='forbid',
        frozen=True,
    )


class PluginAuthor(_ManifestModel):
    name: str | None = None
    mail: str | None = None
    website: str | None = None
    social: dict[str, str] | None = None


class PluginDependency(_ManifestModel):
    """A dependency on another HubPlatform plugin."""

    plugin_id: str = Field(
        min_length=1,
        pattern=r'^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$',
    )
    version: ManifestSpecifier = Field(default_factory=SpecifierSet)


class PluginManifest(_ManifestModel):
    """Immutable declarations shipped with a plugin artifact.

    Runtime state deliberately does not live in a manifest. ``python_dependencies``
    describe distributions installed into the shared plugin environment, while
    ``plugin_dependencies`` form a separate graph used to order plugin activation.
    """

    manifest_version: Literal[1]
    plugin_id: str = Field(
        min_length=1,
        pattern=r'^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$',
    )
    name: str = Field(min_length=1)
    plugin_version: ManifestVersion
    entry_point: str = Field(pattern=r'^([a-zA-Z_][a-zA-Z0-9_]*\.)+[a-zA-Z_][a-zA-Z0-9_]*$')
    description: str = ''
    descriptions: dict[str, str] = Field(default_factory=dict)
    author: PluginAuthor | None = None
    home_page: str | None = None
    app_version: ManifestSpecifier = Field(default_factory=SpecifierSet)
    python_dependencies: tuple[ManifestRequirement, ...] = Field(default_factory=tuple)
    plugin_dependencies: tuple[PluginDependency, ...] = Field(default_factory=tuple)
    locales_path: str | None = None

    @field_validator('descriptions')
    @classmethod
    def validate_descriptions(cls, value: dict[str, str]) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for locale, description in value.items():
            locale = locale.strip().lower()
            if not locale:
                raise ValueError('Description locale must be non-empty.')
            if not description.strip():
                raise ValueError(f'Description for locale {locale!r} must be non-empty.')
            descriptions[locale] = description
        return descriptions

    @field_validator('plugin_dependencies')
    @classmethod
    def validate_plugin_dependencies(
        cls,
        value: tuple[PluginDependency, ...],
    ) -> tuple[PluginDependency, ...]:
        seen: set[str] = set()
        for dependency in value:
            if dependency.plugin_id in seen:
                raise ValueError(f'Duplicate plugin dependency {dependency.plugin_id!r}.')
            seen.add(dependency.plugin_id)
        return value

    @field_validator('locales_path')
    @classmethod
    def validate_locales_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('locales_path must point inside the plugin directory.')
        return value

    def get_description(self, locale: str | None = None) -> str:
        if locale is None:
            return self.description
        return self.descriptions.get(locale.lower(), self.description)
