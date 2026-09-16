from __future__ import annotations


__all__ = [
    'LocalPluginArtifactFetcher',
    'PluginArtifactFetcher',
    'PluginRepositoryBinding',
]


import re
from typing import Protocol
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .base import PluginsRepository
from .types import PluginRelease
from ..installer import PluginArtifact
from ..exceptions import PluginArtifactError


class PluginArtifactFetcher(Protocol):
    """Turns repository release metadata into a local artifact."""

    async def fetch(self, release: PluginRelease) -> PluginArtifact: ...


@dataclass(frozen=True)
class PluginRepositoryBinding:
    repository: PluginsRepository
    fetcher: PluginArtifactFetcher


class LocalPluginArtifactFetcher:
    """Fetcher for plain filesystem paths and ``file://`` URIs."""

    async def fetch(self, release: PluginRelease) -> PluginArtifact:
        if re.match(r'^[a-zA-Z]:[\\/]', release.artifact_uri):
            return PluginArtifact(
                path=Path(release.artifact_uri),
                source=release.artifact_uri,
                expected_sha256=release.sha256,
            )

        parsed = urlparse(release.artifact_uri)
        if parsed.scheme not in ('', 'file'):
            raise PluginArtifactError(
                f'Unsupported artifact URI scheme {parsed.scheme!r}; '
                'inject an application-specific PluginArtifactFetcher.'
            )

        if parsed.scheme == 'file':
            uri_path = unquote(parsed.path)
            if parsed.netloc:
                uri_path = f'//{parsed.netloc}{uri_path}'
            path = Path(url2pathname(uri_path))
        else:
            path = Path(release.artifact_uri)

        return PluginArtifact(
            path=path,
            source=release.artifact_uri,
            expected_sha256=release.sha256,
        )
