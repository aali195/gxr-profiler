# Apps, installer & services guide

[Back to README](../README.md) | [Commands](COMMANDS.md) | [Diagnostics](DIAGNOSTICS.md) | [Background processes & debloat](gxr-findings/debloat.md)

The **Tools > Apps** tab lists the packages installed on the headset and lets you disable or
remove them after an explicit confirmation. The separate **Tools > Installer** tab stages and
installs APK/OBB/XAPK files. Apps, Installer and **Tools > Settings** are the only parts of
gxr-profiler that can change the headset; recording, preview, diagnostics and report export
remain read-only.

> The tool uses Android's package manager (`pm`) through ADB. It does **not** delete files
> from the system image. Stock/system packages are removed for user 0 only and can normally
> be restored with **Restore**.

## Quick start

1. Connect the headset over ADB and open **Tools > Apps**.
2. Use the filters or search box to find a package.
3. Select a package to open its details in a dialog.
4. Press **Disable**, **Enable**, **Remove for user 0**, **Restore** or **Uninstall** in that dialog.
5. Read the confirmation dialog and tick any required data-loss acknowledgement box.
6. Press the confirmation button.

To install software, open **Tools > Installer**, choose or drop the files, review the plan, and
confirm. See [Installing APKs and OBB data](#installing-apks-and-obb-data).

After an action the list refreshes and the raw package-manager result is shown under
**Last action**. Every action is also appended to `reports/apps/app-actions.jsonl` next to
the executable.

## Installing APKs and OBB data

The **Tools > Installer** tab stages files locally and shows a review before anything is sent to the
headset. Nothing is installed until you review the plan and tick the confirmation box.

### Supported inputs

| Input | What happens |
|---|---|
| `.apk` | One APK is installed with `adb install`. Selecting several APKs for the same package installs them as one split set with `adb install-multiple`. |
| `.obb` | The package is inferred from the standard `main.<version>.<package>.obb` or `patch.<version>.<package>.obb` name, or from an `Android/obb/<package>/` folder. You can edit the target package before installing. |
| `.xapk` | The archive is inspected, its `.apk` and `.obb` entries are extracted to staging, and the usual review/confirmation flow runs. `manifest.json` is used when present; APK manifests are the fallback. |
| `.apks`, `.aab`, `.apkm` | Not supported. `.apks`/`.aab` need device-specific split selection or bundletool, and encrypted `.apkm` archives are not readable. |

You can select individual files, choose a whole folder, or drop files/folders onto the installer.
Only `.apk`, `.obb` and `.xapk` files are uploaded; unrelated files are ignored and counted in the
tab.

### Workflow

1. Open **Tools > Installer**.
2. Add files with **Choose files**, **Choose folder**, or drag and drop.
3. Check the staged list. Each row shows the detected package, version, size and SHA-256. OBB
   rows show the target package and the destination path.
4. Choose the install options:
   - **Replace the existing app** (`-r`, on by default) keeps app data when updating.
   - **Allow a downgrade** (`-d`, off by default).
   - **Grant all runtime permissions** (`-g`, off by default).
5. Press **Review install**. The review shows warnings, errors and the exact commands.
6. Tick the confirmation box and press **Install**.
7. Watch the step list. Large OBB pushes can take several minutes. You can switch tabs; the job
   continues and a toast reports the result.

### Package and split detection

- The APK's `AndroidManifest.xml` is read locally. The package name, version code and split name
  are used to group files and to match OBBs.
- If several APKs share a package, they are installed as one split set. A single APK whose
  manifest says it is a split is rejected; add the base APK.
- If an APK's manifest cannot be read at all, it is marked **not a readable APK** and the review
  blocks it. If the manifest is readable but the package name is empty, the tool warns and lets
  Android try anyway. Android still verifies signatures, but the critical-package guard cannot
  inspect an unknown package.
- OBB filenames use the standard `main.<versionCode>.<package>.obb` or
  `patch.<versionCode>.<package>.obb` form. A version mismatch with the APK or the installed app
  is reported as a warning; some games ignore OBB files whose version does not match.
- OBB files are pushed only after the APK install succeeds, to
  `/sdcard/Android/obb/<package>/<original-name>`. The remote size is checked after the push.
- If you select only OBB files, the target package must already be installed, or you must include
  its APK in the same batch.

### Commands used

```sh
adb install -r --user 0 <base.apk>
adb install-multiple -r --user 0 <base.apk> <split_config.arm64_v8a.apk>
adb shell mkdir -p /sdcard/Android/obb/<package>
adb push <main.123.com.example.obb> /sdcard/Android/obb/<package>/main.123.com.example.obb
adb shell stat -c %s /sdcard/Android/obb/<package>/main.123.com.example.obb
```

The actual command also includes `-d` and `-g` when those options are enabled. Every install is
verified with `pm path <package>`; every OBB is verified with `stat`.

### Safety and limits

- Uploads are streamed to a staging folder under `apps-staging/`, hashed with SHA-256, and
  checked against the local free space. The staging folder is ignored by Git.
- Per-file upload limit: 32 GB. Staged session limit: 64 GB and 64 files. XAPK uncompressed limit: 64 GB.
- Staged files are deleted after a successful install, when you press **Discard staged files**, and
  at startup. A failed install keeps them so **Retry** does not require uploading again.
- Reloading the page restores the staged list and current install job from the local server. The job
  itself is in memory, so restarting the profiler loses its status.
- Installs are blocked while a recording is running and while another install is in progress.
- Critical packages cannot be installed over or targeted by an OBB push.
- Archive entries with absolute paths, `..`, encryption, or too many files are rejected.
- APKs are **not** scanned for malware. Android's signature check is the final authority; only
  install files you trust.
- If a batch contains several packages and one fails, the job stops at the failed step. Earlier
  packages in that batch may already be installed; the step list shows exactly what ran.
- Every install attempt is appended to `reports/apps/app-actions.jsonl` with filenames, sizes, hashes,
  options and the ADB output.

### Install troubleshooting

| Symptom | What to try |
|---|---|
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | The installed app was signed with a different key. Uninstall the existing app first, which removes its data, then install again. |
| `INSTALL_FAILED_VERSION_DOWNGRADE` | Enable **Allow a downgrade** in the install options. |
| `INSTALL_FAILED_INSUFFICIENT_STORAGE` | Free space on the headset. The installer blocks a batch larger than the free space it can read. |
| `INSTALL_FAILED_MISSING_SPLIT` | Add the missing split APKs. Select the whole split set from the same source. |
| `INSTALL_FAILED_INVALID_APK` | The file is truncated, corrupt, or not an APK. Re-download it. |
| OBB is not used by the game | Check that the filename's version matches the installed app, that the package matches, and that the file is under `/sdcard/Android/obb/<package>/`. |
| `adb push` is denied | Make sure the device is unlocked and the ADB connection is authorized. The tool creates the OBB folder with `mkdir -p` first. |
| XAPK has no usable APKs | The archive may be encrypted or use an unsupported variant. Extract it and add the APK/OBB files directly. |

## What is shown

Android does not expose reliable human-readable app labels through shell, so package IDs are
the primary name. The list shows:

| Field | Meaning |
|---|---|
| Package | Android package ID; version code, UID and process count are folded in |
| Type | `User`, `System`, or `System (updated)` |
| State | `Enabled`, `Disabled`, or `Removed for user 0` |
| Running | Whether matching processes are currently running |
| OOM | Most important OOM class among matching processes |
| Size | Sortable active APK/install-directory size |
| CPU 5m | Sortable summed CPU percentage from `dumpsys cpuinfo` |
| RSS / GPU mem | Sortable summed process RSS and GPU memory |
| Threads | Sortable summed process thread count |
| Installer | Installing package, e.g. Play Store (rightmost column) |

**Size** uses `du -sk` on the active install path (the `/data/app` package directory when
updated, otherwise the base APK). It excludes app data/cache, which remain in the root detail view.

The header also shows snapshot totals for **CPU 5m**, **RSS**, **GPU mem** and **Size**
across the listed packages.

### Process usage snapshot

The usage columns show a one-shot process snapshot from the same fetch:

- **CPU 5m** is the ~5-minute value from `dumpsys cpuinfo`, summed across matching processes.
- **RSS** is the sum of matching process RSS from `ps`; it is not unique/shared-memory usage.
- **GPU mem** is summed per-process GPU memory from `dumpsys gpu`. Android does not expose
  per-process GPU utilisation through this shell source.
- **Threads** and **OOM** come from `/proc/<pid>/stat` and `/proc/<pid>/oom_score_adj`.
- The process count and process names come from the same snapshot.
- Matching uses the package-style process name (`com.foo` or `com.foo:service`).
- It is not live: press **Refresh** to take a new snapshot.

Selecting a package adds detail from `dumpsys package`, `pm path` and the process snapshot:

- Version name and code, min/target SDK.
- First install and last update time.
- Code path, data directory, primary ABI and package flags.
- Requested permission count.
- Per-user installed state.
- APK paths (including split APKs).
- Matching process names and total CPU, RSS, GPU memory, threads and OOM class.

### System vs user vs stock apps

- **User** packages were installed by the user or an app store. They can be disabled or fully
  uninstalled.
- **System** packages are part of the factory image. Android Settings normally does not offer
  uninstall for these. The Apps tool can disable them or remove them for user 0; the factory
  APK stays in the image and **Restore** can reinstall it for user 0.
- **System (updated)** packages are factory packages with an update installed under `/data`.
  They are treated as system packages for safety.

Critical packages are protected by the tool itself: **Disable**, **Remove for user 0** and
**Uninstall** are not offered for them. The entry stays visible with a **Critical** badge so the
reason is clear, and **Enable**/**Restore** remain available where applicable. The tool does not
attempt to bypass protection by deleting files or remounting the system partition.

## Actions

| Action | Command used | Reversible? | Notes |
|---|---|---|---|
| Disable | `pm disable-user --user 0 <pkg>` | Yes, with Enable | Stops the package's components for user 0. |
| Enable | `pm enable --user 0 <pkg>` | n/a | Re-enables a disabled package. |
| Remove for user 0 | `pm uninstall --user 0 <pkg>` | Yes, with Restore for system packages | Keeps the factory APK in the system image. User data may be deleted. |
| Restore | `cmd package install-existing --user 0 <pkg>` | n/a | Restores an existing system package for user 0. Does not restore deleted data. |
| Uninstall | `pm uninstall <pkg>` | No (reinstall from source) | Only shown for user-installed packages. Removes the app and its data. |

The action buttons are only offered when the package state supports them. The backend also
re-validates the package and action before running anything, and rejects destructive actions
for critical packages even if the API is called directly.

## Performance overrides (Game Mode)

For packages that support Android game modes, the detail dialog also shows **Performance
overrides**:

```sh
cmd game list-modes <package>
cmd game list-configs <package>
cmd game set --fps 90 --downscale 0.8 <package>
cmd game reset <package>
```

- **FPS cap**: 30, 45, 60, 90 or Off.
- **Render scale**: 90%, 80%, 70%, 60%, 50% or Off.
- **Apply** sets a custom Game Mode intervention.
- **Reset** removes the intervention and restores the device configuration.

This uses Android's Game Mode interventions, not a general per-app resolution control. It is only
offered when `cmd game list-modes` reports `custom` support. On this build that is limited to a
few titles, such as Beat Saber, Moonlight XR, NBA 2K and Suzerain; most apps report
`unsupported`.

The render scale is a buffer scale factor, not an exact pixel resolution. The documented FPS
values do not include 72 Hz. The app must be restarted after applying a downscale. Critical
packages are read-only for performance changes, and every change is confirmed and appended to
`reports/apps/app-actions.jsonl`.

## Confirmation and critical packages

Every action opens a dialog with the package ID, an explanation, and the exact command that
will run. Data-loss actions (remove for user 0 and uninstall) require an acknowledgement checkbox.

The critical list follows the [do-not-disable guidance](gxr-findings/debloat.md#do-not-disable):
SystemUI, OpenXR/XR broker components, Play services, WebView, perception/calibration packages,
the XR launcher, network stack, Wi-Fi overlays, `com.qualcomm.*` and `vendor.*` components.

- **Disable**, **Remove for user 0** and **Uninstall** are blocked for critical packages.
- **Enable** and **Restore** remain available so a previously changed package can be recovered.
- All actions are blocked while a recording is in progress.

## Root details (optional)

The core actions use normal shell `pm`; root is **not** required.

When **Root details** is enabled in a package detail view, gxr-profiler uses read-only `su -c`
to show app data and cache size:

```sh
su -c id
su -c 'du -sk /data/user/0/<pkg> /data/user_de/0/<pkg> /data/user/0/<pkg>/cache 2>/dev/null'
```

Root is never requested automatically. Enabling root details may show a KernelSU/Magisk prompt.
Root does not unlock deletion of protected system APKs; the tool deliberately does not remount
or modify the system image.

## Safety

- Recording, live preview, diagnostics and exported reports remain read-only.
- Apps and Installer actions only run after a local UI action with the local API token and a
  confirmation flag in the request. Critical packages cannot be installed over, disabled, removed
  for user 0 or uninstalled.
- Package IDs are validated and shell-quoted before use. Install filenames are validated and
  uploaded bytes are stored under the tool's staging folder; client-supplied paths are never
  executed.
- There are no free-form shell commands in the UI or API.
- Actions and installs are appended to `reports/apps/app-actions.jsonl`. That file is local and is
  not included in exported HTML reports.
- Apps management is not available in offline HTML reports.

## Troubleshooting

| Symptom | What to try |
|---|---|
| `no adb device` | Reconnect wireless ADB, or pass `--serial`. |
| `could not list packages` | Reconnect ADB and press **Refresh**. Check that `pm list packages` works in `adb shell`. |
| Action says `Failure [...]` | Android rejected the change. The package may be protected, already removed, or not support the action in its current state. |
| Package disappeared after removal | Switch the filter to **Removed** and press **Restore** (system packages only). |
| Data size is blank | Enable **Root details**; root may be unavailable or denied by SELinux. |
| A feature broke after disabling a package | Re-enable it in the **Removed**/disabled view or **Restore** it, then reboot the headset if needed. |

For debloat context and package lists, see [background processes & debloat](gxr-findings/debloat.md).
