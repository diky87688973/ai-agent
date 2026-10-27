**English** | [中文](software-update.zh.md)

# Software update

Status: implemented.

## 1. Boundary

The updater replaces program files in the install root. It does not patch a running process, force an update, or ship binary deltas.

Goals:

```text
check the stable channel and stage a newer version automatically
apply only after the user clicks the update button
ship a complete zip package
verify package size and SHA-256
stage and switch with a persisted phase marker and a backup
roll back when the health check fails or a switch is interrupted
remove the downloaded zip after staging
keep one previous version as the rollback point
never write data/; merge *.ini configuration
```

Out of scope:

```text
binary deltas
automatic updates on platforms other than Windows
updates from a source checkout
signature verification
```

## 2. Operating constraints

```text
entry: agent-gui.exe in the install root
launcher: starts agent.gui.launcher from the install root
version source: VERSION in the install root
configuration: config.ini, plugins.ini, plugins.cli.ini,
               plugins.headless.ini, web-ui-config.ini
user data: data/
build: the release workflow builds agent-gui.exe, the update pack, and the full pack
```

The launcher never reads a version pointer; it always starts the program from the install root.

Rejected operations:

```text
overwrite agent-gui.exe in place while another process holds it open
overwrite program files while the GUI is running
write to data/
update a source checkout
```

## 3. Version contract

`VERSION` is the only version source. The header badge and the updater read it.

Format:

```text
major.minor.patch
```

The parser also accepts an optional prerelease suffix; release versions use the three-part form.

Comparison:

```text
only manifests with channel=stable are considered
the remote version must be greater than the local version
the header badge, file timestamps, and dependency versions are not compared
```

## 4. Release contract

Each release contains:

```text
ai-agent-<version>-update-pack-windows.zip
ai-agent-<version>-full-pack-windows.zip
manifest.json
```

Only Windows packages are built. Package names carry the platform; the manifest has no platform field.

`manifest.json`:

```json
{
  "schema": 1,
  "app": "ai-agent",
  "version": "0.2.0",
  "channel": "stable",
  "published_at": "",
  "asset": {
    "name": "ai-agent-0.2.0-update-pack-windows.zip",
    "size": 12345678,
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "notes": []
}
```

`parse_manifest` requires `schema=1`, `version`, `channel`, and `asset`. `asset.name` is reduced to its base name; `asset.size` must be between 1 byte and 1 GiB; `asset.sha256` must be 64 hexadecimal characters. `manifest.json` is limited to 256 KiB. `published_at` and `notes` are metadata; the interface does not render them.

Integrity:

```text
asset.size   = byte length of the zip
asset.sha256 = SHA-256 of the zip
```

The client verifies the zip against both values. It does not verify a detached manifest digest or a signature; the manifest is fetched over HTTPS.

The two zips and `manifest.json` are release assets. The client uses `manifest.json` as the version and integrity source.

## 5. Install layout

The install root is the only run directory; there are no version subdirectories.

```text
install_root/
  agent-gui.exe
  agent/
  plugins/
  assets/
  catalog/
  launcher/
  scripts/
  rules/
  skills/
  VERSION
  config.ini
  plugins.ini
  plugins.cli.ini
  plugins.headless.ini
  web-ui-config.ini
  data/
  updates/
    apply.json          pending apply request
    download/           zip download; removed after staging
    staging/<version>/  extracted payload and .ready marker
    backup/<version>/   previous program files
    launcher/           archived agent-gui.exe
    state.json          persisted switch phase
    update.log
```

Before each start the launcher runs `python -m agent.update.recover`. When the GUI exits and `updates/apply.json` exists, the launcher runs `python -m agent.update.apply`, then repeats.

Update sequence:

```text
staging holds the extracted payload
the helper backs up non-runtime program files to updates/backup/<old_version>
the helper writes the payload over the install root
*.ini files are merged, other files are replaced
on success, staging and download are removed
on failure, the backup is restored
```

`old_version` is the value of `VERSION` before the switch.

## 6. Update states

The controller reports these fields: `available`, `staged`, `detail`, `current`, `remote`, `channel`, `version`, and `interval_minutes`.

`detail` values:

```text
idle
disabled
dev_checkout
check_failed: <exception type>
channel_mismatch
up_to_date
available
download_failed: <message>
staged
restarting
```

`available` is true when the remote stable version is newer. `staged` is true when `updates/staging/<version>/.ready` exists. A failed automatic download leaves `available=true`; the new version is not marked staged.

`updates/state.json` persists the switch phase:

```text
switching    backup and copy in progress
healthy      the target version passed the health check
rolled_back  the backup was restored
```

Fields:

```text
phase
from_version
to_version
detail
```

`updates/apply.json` is only a pending request with `version` and `staging`; the helper removes it after it runs. The switch is not an atomic directory swap: the phase marker and backup make an interrupted per-file copy recoverable.

## 7. Interface

The update button is in the header, left of the theme toggle. It is hidden by default.

Labels:

```text
available, staged       重启更新 v<version>
available, not staged   更新 v<version>
check failed            更新检查失败
otherwise               hidden
```

Click behavior:

```text
check failed  retry POST /api/update/check immediately
staged        POST /api/update/apply; the GUI exits
not staged    POST /api/update/download, then POST /api/update/apply in the same click
```

In the normal flow the page check stages a newer version and shows `重启更新 vX`; one click applies it and restarts the application. If the automatic download failed, the button becomes the download action; that click downloads and applies in one step.

The button is the only update UI element. It does not render a card, package size, update notes, a cancel action, or a separate restart confirmation. Before apply, the backend refuses when background tasks are active or the conversation queue has pending messages; the page changes the label to `更新失败` and puts the error in the button title.

The check runs asynchronously from the page after load and does not block application startup.

Status and button:

```text
idle, disabled, up_to_date, channel_mismatch, dev_checkout   hidden
available                                                     visible
check_failed                                                  visible with error style
```

### 7.1 Check timing

After the page loads, the client calls `POST /api/update/check`. After each response it schedules the next check after `interval_minutes`.

```ini
[update]
check_interval_minutes = 30
```

The range is 1 to 1440 minutes; the default is 30. Out-of-range values are clamped.

A failed check shows the error button. Clicking it retries immediately; the interval timer resumes after the response.

## 8. End-to-end flow

### 8.1 Check

```text
POST /api/update/check
read check_interval_minutes
skip when the install root is a dev checkout
fetch manifest over HTTPS (45 s timeout)
parse schema, version, channel, and asset metadata
reject channel != stable
compare the remote version with VERSION
when newer and not staged: download, verify, extract
return status
```

A newer version is downloaded and staged in the same request. Manifest fetch and parse failures are logged and returned as status; they do not raise to the page and do not block startup.

### 8.2 Download

```text
updates/download/<asset.name>
```

The asset URL is resolved against the manifest URL. The download uses HTTPS, a 30 s timeout, and writes directly to the final file name; there is no temporary file rename. Bytes beyond `asset.size` are rejected. After the download, `verify_asset` checks the size and SHA-256; a mismatch removes the staging directory and fails.

The zip is removed in a `finally` block, so it does not remain after a successful or failed staging attempt. The staging directory is `updates/staging/<version>/`; `.ready` is written last. An existing staging directory is cleared first. A staged version does not stop the check timer: a newer version replaces it when staging succeeds, and only the newest staging directory is kept.

### 8.3 Verify and extract

```text
asset size
asset SHA-256
zip CRC
```

Extraction limits:

```text
20000 entries
1 GiB total uncompressed size
```

Path checks reject empty, absolute, drive-letter, and `..` entries. Each resolved target must stay under the staging version directory. Entries are written as regular files; symlinks are not recreated. No per-file hash list is used.

### 8.4 Apply

`POST /api/update/apply` first checks that no background task is active and no queued message is pending. The controller then writes `updates/apply.json`, sets `detail=restarting`, and exits the GUI process after 0.6 s. After the GUI exits, the native launcher sees `apply.json` and runs the helper.

In an installed tree, the root `agent/update/apply.py` only bootstraps: it reads `apply.json` and runs `staging/<version>/payload/agent/update/apply.py`. If the payload helper is missing, it continues with the root copy.

The helper:

```text
requires staging/.ready and an agent/ directory under the payload
writes state phase=switching with from_version and to_version
backs up non-runtime files to updates/backup/<from_version>
copies payload files; merges *.ini; archives a locked agent-gui.exe
writes VERSION
runs the health check
```

The GUI has already exited; the helper does not stop background tasks itself. The apply route refuses to start when they are active.

### 8.5 Health check

```text
python -m agent.update.health
```

The helper runs it with the install root as working directory and as `AI_AGENT_HEALTH_ROOT`, with a 30 s timeout.

Checks:

```text
import agent.app and agent.entry.web
parse VERSION
parse config.ini when present
parse every plugins/*/plugin-config.ini
bind a loopback TCP port
```

The check does not test data I/O, the tool registry, or the HTTP health endpoint.

Pass:

```text
phase=healthy
remove staging and download
keep the backup
```

Fail:

```text
restore updates/backup/<from_version>
write phase=rolled_back
remove staging
keep update.log
```

When an old launcher is still running after a successful health check, the helper waits 3 s, terminates it, removes the archived executable, and starts the new GUI.

### 8.6 Crash recovery

The launcher runs `python -m agent.update.recover` before every start.

When `phase=switching`:

```text
health check passes -> phase=healthy
health check fails  -> restore the backup, phase=rolled_back, remove staging
```

`phase=healthy` and `phase=rolled_back` are cleared on recovery. Recovery also removes launcher archives.

The switch has no atomic directory swap. A crash during the copy can leave a mix of old and new files; the phase marker and backup make that state recoverable, and the health check decides whether the copied tree is usable.

## 9. Backup and cleanup

The backup contains every non-runtime file. `data/` and `updates/` are excluded. Only one backup is kept: creating a new backup removes other entries under `updates/backup/`.

```text
success: remove staging and download; keep the backup; remove launcher archives
failure: keep the backup for restore; remove staging; keep update.log
```

The zip is removed at the end of staging, not after a successful update. No `versions/` directory is kept.

## 10. Data and configuration

### 10.1 Package contents

Both packs enumerate the project tree and include every file not excluded by `scripts/pack_common.py`. The update pack stores files under `payload/`; the full pack stores them under `ai-agent-<version>-full-pack-windows/`. `VERSION` is written from the build argument instead of being copied.

Excluded paths:

```text
root only: data/ updates/ versions/ dist/ build/ archive/ tmp/ artifacts/
           screenshots/ logs/ docs/ tests/
any level: .git/ .github/ .venv/ venv/ env/ __pycache__/ .ruff_cache/
           .pytest_cache/ .mypy_cache/ .locks/ coverage_html/ htmlcov/
           *.egg-info/
files:     .coverage .DS_Store Thumbs.db _PRIVATE_RULE.md
suffixes:  .pyc .pyo .raw .log .tmp .bak .orig .rej .obj .res .o .pdb .example
secrets:   .env *.local.ini *.local.toml *.pem *.key *.p12 *.pfx
           plugins/multi_model/plugin-config.ini
```

Root-only entries match the first path segment; a directory such as `plugins/<name>/data/` is packaged. The update pack has no path allowlist; every packaged file is applied at its path.

### 10.2 Apply rules

Regular files replace the file at the same path. `*.ini` files are merged by key.

Merge rules:

```text
start from the incoming template
for each section and key in the template, keep the existing value when present
drop sections and keys that are absent from the template
write through a temporary file and replace
```

A missing file is copied from the template. This is not a full overwrite: user values for matching keys survive, but user-only sections and keys do not. When an existing file is merged, comments are not preserved; the merged file is written from the template sections and keys.

`data/` and `updates/` are runtime directories; they are neither backed up nor written. Packages cannot express deletions; apply only writes and merges. Sensitive configuration is excluded from the package and stays as it is.

When copying `agent-gui.exe` fails because the file is locked, the helper renames it to `updates/launcher/agent-gui.exe.old-<timestamp>` and writes the new file; a failed copy renames it back. When the health check fails, `restore_backup` restores the backup and removes non-runtime files that the backup does not contain.

Non-sensitive plugin configuration is carried by the package. A missing local INI file is created from the package template; the updater does not synthesize a configuration that the package does not contain.

## 11. Development mode

Update is disabled when either condition holds:

```text
.git exists in the install root
AI_AGENT_DEV is 1, true, yes, or on
```

The check returns `dev_checkout`, downloads nothing, and leaves the button hidden. Packaged installs exclude `.git`.

## 12. Platform scope

```text
Windows  implemented; update and full packs are built
macOS    not implemented
Linux    not implemented
```

Package names carry the platform suffix. The release workflow produces only Windows packages. No launcher or package exists for the other platforms.

## 13. Security

Implemented controls:

```text
HTTPS for the manifest and the asset
asset size and SHA-256
safe extraction with path, file-count, and size limits
no symlink recreation
data/ and updates/ excluded from the payload
*.ini key merge; sensitive configuration excluded
```

Limits:

```text
no signature
no detached manifest digest
```

HTTPS protects transport. SHA-256 detects download corruption, but it does not prevent a replaced release asset; a party that can replace the release can replace both the manifest and the zip. The update endpoints require the admin scope, and no model-facing capability exposes update actions.

## 14. Module layout

```text
agent/update/
  __init__.py
  version.py        version read and comparison
  manifest.py       manifest parsing and asset verification
  checker.py        remote check
  stage.py          download, hash, and safe extraction
  install.py        backup, copy, restore, and cleanup
  apply.py          helper entry
  config_merge.py   key-level INI merge
  health.py         post-switch self-check
  logs.py           JSON Lines update log
  processes.py      old launcher discovery, stop, and relaunch
  recover.py        startup recovery
  state.py          updates/state.json
  assets.py         sensitive and local file classification

agent/shell/web/web_routes.py
  GET  /api/update/status
  GET  /api/update/logs
  POST /api/update/check
  POST /api/update/download
  POST /api/update/apply

agent/shell/web/web_assets/classic/js/shell/update.js
launcher/launcher.cpp
scripts/pack_common.py
scripts/build_release.py
scripts/build_full_pack.py
```

No model-facing update capability is registered.

## 15. Release and CI

Pushing a `v*` tag starts the release workflow:

```text
check VERSION equals the tag without the leading v
build agent-gui.exe with launcher/build.ps1
build the update pack and manifest with scripts/build_release.py
the manifest records the zip size and SHA-256
build the full pack with scripts/build_full_pack.py
upload both zips and manifest.json to the release
```

The generated manifest sets `published_at` to an empty string and `notes` to an empty list. It does not generate a signature, a detached manifest digest, or a checksum file. Only Windows assets are produced.

## 16. Verification

```text
version comparison: older / same / newer / prerelease
dev checkout: no update button
remote unreachable: check_failed status; explicit retry
manifest schema invalid: reject
asset size or SHA-256 mismatch: reject
zip path traversal: reject
zip file-count or uncompressed-size limit: reject
interrupted download: staging and zip removed; retry succeeds
apply with active background tasks: refused
apply with pending queued messages: refused
health check failure: restore backup
*.ini merge keeps user values and drops removed keys
new payload files are installed
data/ survives update and rollback
crash during switching: recover completes or rolls back
rolled-back version starts
staging and zip cleaned after staging
one backup retained
```

## 17. Update log

`updates/update.log` is JSON Lines. Each row has `ts`, `event`, and `level`, plus event fields. The file rotates at 1 MiB to `update.log.1`; one generation is kept.

Events include:

```text
check_start
check_skip
check_result
download_start
download_staged
apply_requested
apply_start
apply_success
apply_failed
apply_health_failed
stage_start
stage_ready
stage_failed
recover_start
recover_rolled_back
```

Failures and cleanup errors are also written with `level=error`. `GET /api/update/logs` returns the last 100 rows by default; the tail is capped at 500. Errors also go to `<data_root>/logs/errors.log`. `update.log` is not removed on failure.
