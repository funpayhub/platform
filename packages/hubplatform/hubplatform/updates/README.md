# Updates

## Purpose
This package lets an app built on hubplatform update itself: find new versions, install them
next to the running version without interrupting it, and hand over to a **launcher** that
switches to the new version on restart and rolls back if it does not start.

What is in hubplatform (this package and `hubplatform.runtime`):

* the **launcher protocol**: how an app and its launcher talk to each other;
* **versions managers**: where versions come from (GitHub releases out of the box);
* **manifests**: the description of a release and its files;
* the **installer**: downloads, verifies and unpacks releases;
* the **installation layout**: what lives where on disk.

What is **not** here: the launcher itself, the release build and CI. They belong to the app
(for FunPay Hub: `launcher.py`, `tools/build_release.py`, `.github/workflows/release.yml`,
described in its `UPDATES.md`). The launcher is a separate program installed once on the user's
machine; it never imports hubplatform.

## Design

### Prebuilt releases
Nothing is resolved, compiled or downloaded from a package index on the user's machine.
CI builds every release completely; installing a release means downloading archives,
checking their hashes and unpacking them. A release consists of two parts:

* **Runtime**: a Python interpreter ([python-build-standalone](https://github.com/astral-sh/python-build-standalone))
  with all third-party packages preinstalled into its `site-packages`. One archive per platform,
  tens of MB. Identified by a **runtime id** (`rt-<hash>`) computed from the Python version and the
  locked third-party packages, so releases that do not change them share one runtime and users
  download it only once.
* **App**: the app code and first-party packages (hubplatform itself) in `lib/`. One zip for all
  platforms, hundreds of KB. A typical update downloads only this.

### Side-by-side installation
Every installed version lives in its own directory and never changes after installation.
The running version is never touched: a new version is installed next to it, and the launcher
switches to it only when the app restarts. The previous version stays installed, so the
launcher can switch back.

### Launcher
The launcher is a small program that starts the current release, restarts it on request,
switches releases and rolls back. It is versioned independently of the app (installed once,
it replaces itself only from a release that already started successfully), so the app and the
launcher communicate only through a small, versioned protocol: exit codes, environment variables
and files. Every rule of this protocol must stay compatible with launchers already installed,
or `LAUNCHER_PROTOCOL` must be bumped (a release may then require a newer launcher, see
`LauncherOutdatedError`).

## Installation layout
```
<working dir>/
    launcher/               launcher's own Python + launcher.py (owned by the app's launcher)
    releases/
        1.4.0/              app: code, lib/, release.json, launcher.py, .installed
        1.5.0/
        .downloads/         archives being downloaded / verified
        state.json          current / previous release       (written by the launcher only)
        staged.json         release to switch to             (written by the app only)
        result.json         outcome of the last switch       (launcher writes, app removes)
        .health             "the app started" signal         (app creates, launcher removes)
    runtimes/
        rt-3f9a1c2b7d4e/    python/ (interpreter + packages), runtime.json, constraints.txt,
                            .installed
    envs/
        rt-3f9a1c2b7d4e/    optional venv on top of the runtime (plugin packages)
    backups/                app data saved before the last switch (launcher)
    storage/ config/ logs/ plugins/
```

Rules:

* A release or runtime directory is **complete only if its `.installed` marker exists**. The
  marker is written last; a directory without it is a leftover of an interrupted installation and
  is removed by the next installation.
* Directories are installed under a temporary name (`.tmp-<name>-<random>`) and renamed into
  place. A venv can not be moved, which is why runtimes are plain interpreters and plugin venvs are
  created in their final location.
* **Every file has exactly one writer**, so the app and the launcher never race on a file.
* Every JSON file is written atomically: to a temporary file, then `os.replace`. On Windows the
  rename is retried for a few seconds, because antivirus, the indexer or OneDrive may briefly
  hold a just written file.
* The app installs releases and runtimes; **only the launcher removes them** (it is the only
  process that knows none of them is running; on Windows a running interpreter locks its files).

`Installation` (`releases.py`) gives the app access to this layout.

## Launcher protocol

### Exit codes
`hubplatform.runtime.ExitCodes`. The app asks the launcher for an action by exiting with:

| Code | Name             | Launcher action                                        |
|------|------------------|--------------------------------------------------------|
| 0    | `SHUTDOWN`       | stop                                                   |
| 100  | `RESTART`        | start the current release again, same mode             |
| 101  | `RESTART_SAFE`   | start again with `--safe`                              |
| 102  | `RESTART_NORMAL` | start again without `--safe`                           |
| 103  | `UPDATE`         | switch to the staged release (`staged.json`), start it |

Any other code is a crash. A crash of a release that has not confirmed it started counts as a
failed start (see [Health check and rollback](#health-check-and-rollback)); a crash of a
confirmed release stops the launcher with that code.

`HubPlatformApp.stop(exit_code)` stops the app and remembers the code in `HubPlatformApp.exit_code`;
the app's entry point exits with it:

```python
await app.run()
sys.exit(app.exit_code)
```

### Environment variables
The launcher sets them for the app; `LauncherEnvironment.from_env()` / `launcher_environment()`
read them (`None` if the app was started without a launcher, e.g. during development).

| Variable                        | Meaning                                          |
|---------------------------------|--------------------------------------------------|
| `HUBPLATFORM_LAUNCHER_PROTOCOL` | protocol version the launcher implements         |
| `HUBPLATFORM_RELEASES_DIR`      | `releases/`                                      |
| `HUBPLATFORM_RUNTIMES_DIR`      | `runtimes/`                                      |
| `HUBPLATFORM_ENVS_DIR`          | `envs/`                                          |
| `HUBPLATFORM_RELEASE`           | version of the running release                   |
| `HUBPLATFORM_RUNTIME`           | runtime id of the running release                |
| `HUBPLATFORM_HEALTH_FILE`       | file to create once the app started              |

The launcher also sets `PYTHONPATH` (the release's `pythonpath` entries) and
`PYTHONNOUSERSITE=1`, and removes `PYTHONHOME` / `VIRTUAL_ENV`.

### Files
All files carry `"schema": 1`.

`state.json` (launcher):
```json
{"schema": 1, "current": "1.5.0", "previous": "1.4.0", "pending": false, "attempts": 0, "failed": ["1.4.1"]}
```
* `pending`: `current` was just switched to and has not confirmed it starts;
* `attempts`: failed starts of the pending release;
* `failed`: releases that were rolled back.

Read with `Installation.read_state()` → `ReleaseState`.

`staged.json` (app): `{"schema": 1, "version": "1.5.0"}`. Written by `Installation.stage()` /
`ReleaseInstaller.stage()`; only an installed release can be staged.

`result.json` (launcher):
```json
{"schema": 1, "status": "updated", "version": "1.5.0", "previous": "1.4.0", "message": null}
```
* `updated`: switched to `version` from `previous` (written when switching, so the new
  release sees it on its first start);
* `rolled_back`: `version` failed to start, switched back to `previous`;
* `failed`: could not switch to `version` (e.g. it is not installed), still on `previous`.

Read and removed with `Installation.pop_result()` → `UpdateResult`; the app should report it to
the user on start.

### Health signal
`hubplatform.runtime.signal_healthy()` creates the health file. `HubPlatformApp.run()` calls it
once setup succeeded and the components' tasks are created (the app enters `RUNNING`); a
component failing later does not undo it. After a switch the launcher waits for it; see below.
Does nothing without a launcher.

### Health check and rollback
(Implemented by the launcher; described here because the app's behaviour drives it.)

1. On `UPDATE` the launcher copies the app data (`storage/`, `config/` by default) to
   `backups/<current>`, sets `current = staged`, `previous = old current`, `pending = true`,
   writes `result.json` (`updated`) and starts the new release.
2. When the health file appears, the release is confirmed: `pending = false`. If the release
   ships a newer launcher, the launcher replaces itself now (used from its next start).
3. If the release exits with a non-action code or does not signal health within 5 minutes,
   it is a failed start. After 2 failed starts the launcher moves the release's data to
   `backups/<version>.failed`, restores `backups/<previous>`, switches back to `previous`,
   adds the version to `failed` and writes `result.json` (`rolled_back`).
4. After every switch the launcher removes releases other than `current` and `previous`, and
   runtimes / envs neither of them uses.

## Manifests
`manifest.py`. All three are produced by the app's release build.

### `manifest.json` (published with every release) → `UpdateManifest`
```json
{
  "schema": 1,
  "version": "1.5.0",
  "launcher_protocol": 1,
  "app": {"url": "https://.../funpayhub-1.5.0.zip", "sha256": "…", "size": 236544},
  "runtime": {
    "id": "rt-3f9a1c2b7d4e",
    "python": "3.15.2",
    "assets": {
      "x86_64-pc-windows-msvc":    {"url": "https://.../runtime-rt-3f9a1c2b7d4e-x86_64-pc-windows-msvc.tar.gz", "sha256": "…", "size": 40278149},
      "x86_64-unknown-linux-gnu":  {"url": "…", "sha256": "…", "size": 41203321},
      "aarch64-unknown-linux-gnu": {"url": "…", "sha256": "…", "size": 39871002}
    }
  }
}
```
Platform keys are python-build-standalone target names; `current_platform()` returns the one of
this machine (`None` for unsupported systems: not x86_64 / aarch64, not Windows / glibc Linux).
`launcher_protocol` is the minimal launcher protocol the release needs.

Validation rejects: unknown schema, invalid versions or runtime ids, non-http(s) URLs, malformed
hashes, non-positive sizes.

### `release.json` (inside every installed release) → `ReleaseInfo`
```json
{"schema": 1, "version": "1.5.0", "runtime": "rt-3f9a1c2b7d4e", "entrypoint": "app.py",
 "launcher_protocol": 1, "pythonpath": ["lib"]}
```
`entrypoint` and `pythonpath` are relative to the release directory (absolute paths and `..` are
rejected). The launcher runs `<runtime python> -s <release>/<entrypoint>` with
`PYTHONPATH=<release>/<pythonpath...>`.

### `runtime.json` (inside every installed runtime) → `RuntimeInfo`
```json
{"schema": 1, "id": "rt-3f9a1c2b7d4e", "python": "3.15.2", "platform": "x86_64-pc-windows-msvc"}
```
Next to it `constraints.txt` pins every package of the runtime; plugin packages are installed
with it as constraints so they can never replace a runtime package.

## Versions managers
`manager/base.py`, `manager/github.py`.

`VersionsManager` is the source of versions:

| Method                          | Description                                                        |
|---------------------------------|--------------------------------------------------------------------|
| `get_versions(from_=None)`      | all versions, newest first; only newer than `from_` if given        |
| `get_latest_version()`          | `AppVersionInfo` of the newest version                              |
| `get_version_info(version)`     | `AppVersionInfo(version, notes, manifest_url)`                      |
| `get_manifest(version)`         | downloads and validates the version's `UpdateManifest`              |
| `download(url, dir, filename, wait=False)` | downloads a file into `dir/filename`                     |
| `is_downloading(dir, filename)` | whether any manager is downloading into that file now              |

`download` writes into `<filename>.<random>` and renames to `filename` only on success. Only one
download into the same file may run at a time across all managers: with `wait=False` a second one
raises `VersionDownloadInProgressError`, with `wait=True` it waits and downloads again.

`manifest_url` is `None` for versions that can not be installed automatically (e.g. released
before automatic updates); `get_manifest` raises `VersionNotInstallableError` for them.

A custom source implements `get_versions`, `get_latest_version`, `get_version_info` and two
transport methods:

```python
class MyVersionsManager(VersionsManager):
    async def _fetch(self, url: str) -> bytes: ...                 # small files (manifests)
    async def _download_file(self, url: str, path: Path) -> None: ...  # big files, into path
```

### GitHub
`GitHubVersionsManager(repo_url, manifest_asset='manifest.json')`:

* versions are releases tagged `vX.Y.Z` (other tags, e.g. `runtime-<id>`, are ignored);
* `notes` is the release description;
* `manifest_url` is the download URL of the release asset named `manifest_asset`;
* manifests are limited to 1 MB.

Use it as an async context manager (it owns an `aiohttp` session).

## Installer
`installer.py`.

```python
installer = ReleaseInstaller.from_launcher(versions_manager)  # None without a launcher
path = await installer.install(version, on_stage=callback)    # releases/<version>
installer.stage(version)
app.stop(ExitCodes.UPDATE)
```

`ReleaseInstaller(versions_manager, installation, launcher_protocol, platform=None)` can also be
created directly (tests, tools). `from_launcher()` takes the paths and the protocol from the
launcher environment.

`install(version, on_stage=None)`:

1. `FETCHING_MANIFEST`: `get_manifest()`; checks the release does not need a newer launcher
   protocol (`LauncherOutdatedError`) and has a runtime for this platform
   (`UnsupportedPlatformError`).
2. Removes leftovers of interrupted installations: `.tmp-*` directories and release / runtime
   directories without `.installed`.
3. If the runtime is not installed:
   * `DOWNLOADING_RUNTIME`: downloads it into `releases/.downloads`, checks size and SHA-256;
   * `INSTALLING_RUNTIME`: unpacks it with `tarfile`'s `data` filter (rejects absolute paths,
     `..`, links outside the target, device files), checks `runtime.json`, runs the interpreter
     (`python -s -c "import sys"`), renames it into `runtimes/<id>`, writes `.installed`.
4. `DOWNLOADING_APP`: downloads the app zip, checks size and SHA-256.
5. `INSTALLING_APP`: unpacks it (rejects absolute paths, `..`, drive letters, backslashes),
   checks `release.json` matches the manifest (version and runtime id), renames it into
   `releases/<version>`, writes `.installed`.

Downloaded archives are deleted after installation, successful or not.

Behaviour:

* already installed versions are returned immediately;
* only one installation runs at a time per installer (`is_installing`); others wait;
* `on_stage` is awaited before every stage; its exceptions are logged and ignored;
* nothing of the running release changes, so an installation can be interrupted at any point;
* errors: `VersionManagerError` subclasses pass through (download, manifest, protocol, platform,
  not installable); anything else is wrapped into `VersionInstallError` with the cause chained.

`stage(version)` writes `staged.json`; raises `ValueError` if the version is not installed.

### Exceptions
`exceptions.py`. All derive from `VersionManagerError` (→ `HubPlatformError`); messages are
`I18nString`s.

| Exception                         | When                                                   |
|-----------------------------------|--------------------------------------------------------|
| `VersionNotFoundError`            | the source has no such version                         |
| `FileDownloadError`               | downloading a file failed                              |
| `VersionDownloadInProgressError`  | the file is being downloaded and `wait=False`          |
| `VersionInstallError`             | installation failed (cause chained)                    |
| `VersionNotInstallableError`      | the version has no manifest                            |
| `LauncherOutdatedError`           | the release needs a newer launcher protocol            |
| `UnsupportedPlatformError`        | the release has no runtime for this platform           |

## Integrating into an app
```python
from hubplatform.runtime import ExitCodes
from hubplatform.updates import GitHubVersionsManager, ReleaseInstaller


async def main() -> int:
    app = HubPlatformApp(version=read_version(), ...)
    async with GitHubVersionsManager('https://github.com/<owner>/<repo>') as versions_manager:
        installer = ReleaseInstaller.from_launcher(versions_manager)  # None in development
        app.app_context.provide('App', 'versions_manager', versions_manager)
        app.app_context.provide('App', 'release_installer', installer)
        await app.setup()
        if installer is not None and (result := installer.installation.pop_result()):
            notify_user(result)          # updated / rolled back / failed
        await app.run()                  # signals health once running
    return app.exit_code                 # ExitCodes.UPDATE after `installer.stage(...)`


sys.exit(asyncio.run(main()))
```

In a UI: list versions with `versions_manager.get_versions(from_=app.version)`, run
`installer.install(version, on_stage=...)` in a background task (it can take a while when a
new runtime is needed), then `installer.stage(version)` and `app.stop(ExitCodes.UPDATE)`.
Warn about versions in `installation.read_state().failed`: they were rolled back before.

## Plugin environments
A runtime is read-only and shared by releases, so plugin packages must not be installed into it.
Instead, a venv is created on top of the runtime:

```
runtimes/<id>/python/python -m venv --system-site-packages envs/<id>
envs/<id>/<bin>/python -m pip install -c runtimes/<id>/constraints.txt <plugin requirements>
```

The venv sees the runtime packages; the constraints make pip fail instead of replacing them.
If `envs/<id>/pyvenv.cfg` exists, the launcher starts the app with that venv's interpreter.
When a release brings a new runtime, plugin packages must be installed into the new env before
switching (compiled packages are tied to the Python version). The launcher supports envs and
removes unused ones; the installer does not create them yet (there is no plugin system yet).
