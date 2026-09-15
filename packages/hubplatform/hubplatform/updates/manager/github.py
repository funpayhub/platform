from __future__ import annotations


__all__ = ['GitHubVersionsManager']


import re
import json
from shutil import copyfileobj
from asyncio import to_thread
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlencode
from urllib.request import Request, urlopen

from packaging.version import Version

from hubplatform.core import convert_exceptions
from hubplatform.i18n import I18nString
from hubplatform.updates import exceptions as exc

from .base import VersionsManager
from ..types import AppVersionInfo


_VERSION_TAG_RE = re.compile(r'v([0-9]+)\.([0-9]+)\.([0-9]+)')
_API_ROOT = 'https://api.github.com'
_API_VERSION = '2026-03-10'
_RELEASES_PER_PAGE = 100
_REQUEST_TIMEOUT = 30


def _request(url: str, accept: str = 'application/vnd.github+json') -> Request:
    return Request(
        url,
        headers={
            'Accept': accept,
            'User-Agent': 'hubplatform',
            'X-GitHub-Api-Version': _API_VERSION,
        },
    )


def _read_json(url: str) -> object:
    with urlopen(_request(url), timeout=_REQUEST_TIMEOUT) as response:
        result: object = json.load(response)
    return result


def _download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with (
            urlopen(
                _request(url, accept='application/octet-stream'),
                timeout=_REQUEST_TIMEOUT,
            ) as response,
            NamedTemporaryFile(
                mode='wb',
                prefix=f'.{path.name}.',
                suffix='.tmp',
                dir=path.parent,
                delete=False,
            ) as temporary_file,
        ):
            temporary_path = Path(temporary_file.name)
            copyfileobj(response, temporary_file)

        assert temporary_path is not None
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class GitHubVersionsManager(VersionsManager):
    def __init__(self, repo_url: str) -> None:
        self._repo_url = repo_url
        owner, repo = self._parse_repo_url(repo_url)
        self._repo = repo
        self._api_repo_url = f'{_API_ROOT}/repos/{quote(owner, safe="")}/{quote(repo, safe="")}'
        self._cache: dict[Version, AppVersionInfo] = {}

    @property
    def repo_url(self) -> str:
        return self._repo_url

    @convert_exceptions(
        except_=exc.VersionManagerError,
        exception_factory=lambda: exc.VersionManagerError(
            'An error occurred while getting latest version.'
        ),
    )
    async def get_latest_version(self) -> AppVersionInfo:
        versions = await self.get_versions()
        if not versions:
            raise exc.VersionManagerError(
                I18nString(
                    key='hubplatform-version-github-no_versions_error',
                    fallback=f'GitHub repo {self._repo_url} does not have any versions yet.',
                    kwargs={'repo_url': self._repo_url},
                )
            )
        return self._cache[versions[0]]

    @convert_exceptions(
        except_=exc.VersionManagerError,
        exception_factory=lambda: exc.VersionManagerError(
            'An error occurred while getting info about version.'
        ),
    )
    async def get_version_info(self, version: Version | str) -> AppVersionInfo:
        version = self._to_version(version)
        if version in self._cache:
            return self._cache[version]

        tag = self._version_to_tag(version)
        url = f'{self._api_repo_url}/releases/tags/{quote(tag, safe="")}'

        try:
            release = await to_thread(_read_json, url)
        except HTTPError as error:
            if error.code == 404:
                raise exc.VersionNotFoundError(
                    version=version,
                    msg=I18nString(
                        key='hubplatform-version-github-version_not_found_error',
                        fallback=f'GitHub repo {self._repo_url} does not have version {version}.',
                        kwargs={'repo_url': self._repo_url, 'version': str(version)},
                    ),
                ) from error
            raise

        version_info = self._parse_release(release)
        if version_info is None or version_info.version != version:
            raise exc.VersionNotFoundError(
                version=version,
                msg=I18nString(
                    key='hubplatform-version-github-version_not_found_error',
                    fallback=f'GitHub repo {self._repo_url} does not have version {version}.',
                    kwargs={'repo_url': self._repo_url, 'version': str(version)},
                ),
            )

        self._cache[version] = version_info
        return version_info

    @convert_exceptions(
        except_=exc.VersionManagerError,
        exception_factory=lambda: exc.VersionManagerError(
            'An error occurred while getting versions list.'
        ),
    )
    async def get_versions(self, from_: Version | None = None) -> tuple[Version, ...]:
        cache: dict[Version, AppVersionInfo] = {}
        page = 1

        while True:
            query = urlencode({'per_page': _RELEASES_PER_PAGE, 'page': page})
            releases = await to_thread(
                _read_json,
                f'{self._api_repo_url}/releases?{query}',
            )
            if not isinstance(releases, list):
                raise ValueError('GitHub returned an invalid releases response.')

            for release in releases:
                version_info = self._parse_release(release)
                if version_info is not None:
                    cache.setdefault(version_info.version, version_info)

            if len(releases) < _RELEASES_PER_PAGE:
                break
            page += 1

        self._cache = cache
        versions = sorted(cache, reverse=True)
        if from_ is not None:
            versions = [version for version in versions if version > from_]
        return tuple(versions)

    async def download_version(
        self,
        version: Version | str | AppVersionInfo,
        path: str | Path | None = None,
    ) -> Path:
        if isinstance(version, AppVersionInfo):
            version_info = version
        else:
            version_info = await self.get_version_info(version)

        filename = f'{self._repo}-{self._version_to_tag(version_info.version)}.zip'
        destination = Path.cwd() / filename if path is None else Path(path)
        destination = destination.expanduser().resolve()
        if destination.is_dir():
            destination /= filename

        await to_thread(_download, version_info.url, destination)
        return destination

    @staticmethod
    def _parse_repo_url(repo_url: str) -> tuple[str, str]:
        parsed = urlsplit(repo_url.strip().rstrip('/'))
        if (
            parsed.scheme != 'https'
            or parsed.hostname not in {'github.com', 'www.github.com'}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f'Invalid GitHub repository URL: {repo_url}.')

        parts = parsed.path.strip('/').split('/')
        if len(parts) != 2:
            raise ValueError(f'Invalid GitHub repository URL: {repo_url}.')

        owner, repo = parts
        repo = repo.removesuffix('.git')
        if not owner or not repo:
            raise ValueError(f'Invalid GitHub repository URL: {repo_url}.')
        return owner, repo

    @staticmethod
    def _version_to_tag(version: Version) -> str:
        tag = f'v{version.major}.{version.minor}.{version.micro}'
        if Version(tag[1:]) != version:
            raise ValueError(f'Version {version} cannot be represented as a vX.Y.Z tag.')
        return tag

    @staticmethod
    def _parse_release(release: object) -> AppVersionInfo | None:
        if not isinstance(release, dict):
            raise ValueError('GitHub returned an invalid release.')

        tag_name: object = release.get('tag_name')
        if not isinstance(tag_name, str):
            return None

        match = _VERSION_TAG_RE.fullmatch(tag_name)
        if match is None:
            return None

        notes: object = release.get('body')
        if notes is None:
            notes = ''
        if not isinstance(notes, str):
            raise ValueError(f'GitHub returned invalid notes for release {tag_name}.')

        url: object = release.get('zipball_url')
        if not isinstance(url, str):
            raise ValueError(f'GitHub returned an invalid URL for release {tag_name}.')

        return AppVersionInfo(
            version=Version('.'.join(match.groups())),
            notes=notes,
            url=url,
        )
