from __future__ import annotations


__all__ = [
    'PluginManifest',
    'PluginAuthor',
    'LoadedPlugin',
]


from typing import Self, Literal
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, BaseModel, field_validator, model_validator
from packaging.version import Version
from packaging.specifiers import SpecifierSet
from packaging.requirements import Requirement


class _WithDescription(BaseModel):
    model_config = {'extra': 'allow'}
    description: str = Field(default='')

    @model_validator(mode='after')
    def validate_descriptions(self) -> Self:
        if not self.model_extra:
            return self

        for k, v in self.model_extra.items():
            if not k.startswith('description_'):
                continue
            if not isinstance(v, str) or len(v.strip()) == 0:
                raise ValueError(f'{k} must be non-empty string.')
        return self

    def get_description(self, locale: str | None = None) -> str:
        if not self.model_extra is not None or locale is None:
            return self.description
        return self.model_extra.get(f'description_{locale.lower()}', self.description)


class PluginManifest(_WithDescription):
    model_config = {'frozen': True, 'arbitrary_types_allowed': True}

    manifest_version: Literal[1]
    plugin_id: str
    name: str
    plugin_version: Version
    entry_point: str = Field(pattern=r'^([a-zA-Z_][a-zA-Z0-9_]*\.)+[a-zA-Z_][a-zA-Z0-9_]*$')
    author: PluginAuthor | None = Field(default=None)
    home_page: str | None = Field(default=None)
    app_version: SpecifierSet
    dependencies: tuple[Requirement] = Field(default_factory=tuple)
    locales_path: str | None = None

    @field_validator('plugin_version', mode='before')
    @classmethod
    def convert_version(cls, value: str | Version) -> Version:
        if isinstance(value, str):
            value = Version(value)
        return value

    @field_validator('app_version', mode='before')
    @classmethod
    def convert_app_version(cls, value: str | SpecifierSet) -> SpecifierSet:
        if isinstance(value, str):
            value = SpecifierSet(value)
        return value

    @field_validator('dependencies', mode='before')
    @classmethod
    def convert_requirements(
        cls, value: list[str | Requirement] | tuple[str | Requirement, ...]
    ) -> tuple[Requirement]:
        if not isinstance(value, list | tuple):
            raise ValueError(
                'Dependencies must be a list | tuple of strings or `Requirement` objects.'
            )
        result = []
        for i in value:
            if isinstance(i, Requirement):
                result.append(i)
            elif isinstance(i, str):
                result.append(Requirement(i))
            else:
                raise ValueError('Each dependency must be a string or `Requirement` object.')
        return tuple(result)


class PluginAuthor(BaseModel):
    model_config = {'extra': 'allow'}

    name: str | None = Field(default=None)
    mail: str | None = Field(default=None)
    website: str | None = Field(default=None)
    social: dict[str, str] | None = Field(default=None)


@dataclass
class LoadedPlugin[PluginCLS]:
    path: Path
    manifest: PluginManifest
    plugin: PluginCLS | None
    error: Exception | None = None
