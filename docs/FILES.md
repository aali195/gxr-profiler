# Files guide

[Documentation home](README.md) | [Manager guide](MANAGER.md) | [Profiler](PROFILER.md) | [CLI](CLI.md)

The **GXR Manager > Files** tab is a local file browser for the headset. It can download and upload
files, create folders, rename, move and delete. Normal reads and shared-storage writes need no root;
enabling **Root** allows the same operations on system paths.

> File operations are blocked while **GXR Profiler** is recording. This includes browsing and
> downloads, so a transfer cannot skew a run.

## Quick start

1. Connect the headset over ADB and open **GXR Manager > Files**.
2. Start at `/sdcard/` or type another absolute path.
3. Use **Download** on a file, or **Upload** to add files to the current folder.
4. Select rows with the checkboxes to enable **Rename**, **Move** and **Delete**.
5. Enable **Root: off** only when you need paths outside shared storage.

## Navigation

- **Home** returns to `/sdcard`.
- **Up** goes to the parent folder.
- The breadcrumb jumps to any parent.
- The path field accepts any absolute Linux path.
- Mouse back and forward buttons move through the folders you have visited.
- Folder names open the folder; file names download the file.
- The list shows type, size and the device's modification time.

## Download and upload

- **Download** streams the file from the headset.
- In the native window, a Windows save dialog opens and defaults to your **Downloads** folder. In browser
  mode, the browser's own download location and prompts apply.
- Progress is shown when the file picker is available. When the native save dialog or browser download
  handles the file, the card shows **In progress** instead of a percentage.
- Large downloads are streamed to disk instead of buffered in memory.
- Symlinks are downloaded as their target file.
- **Upload** sends one or more files into the current folder. The bar shows the browser-to-app transfer,
  then switches to **Writing to headset...** while the file is pushed and verified.
- Uploads are written to a temporary name first, then moved into place, so a failed transfer does
  not leave a partial file under the final name.
- If the name already exists, the app asks before replacing it.
- Uploads are limited to 8 GB per file.

## New folder, rename and move

- **New folder** creates one folder in the current directory.
- **Rename** works on one selected item. The item stays in the same folder.
- **Move** sends the selected items to another folder. Enter the destination path in the dialog.
- Moving a folder into itself or into one of its subfolders is rejected.
- Name conflicts ask before replacing.

## Delete and protected paths

- Select one or more items, then press **Delete**.
- Deleting a folder removes everything inside it; the dialog says so explicitly.
- **With root enabled, type `DELETE` to confirm.**
- These paths and their critical subtrees are refused even with root:
  `/`, `/system`, `/vendor`, `/product`, `/apex`, `/metadata`, `/persist`,
  `/data`, `/data/system`, `/data/app`, `/data/misc`, `/data/vendor`, `/data/adb`,
  `/data/user`, `/data/user_de`, `/data/local`, `/data/dalvik-cache`,
  `/data/tombstones`, `/data/media`, `/storage`, `/sdcard`, `/mnt`, `/proc`, `/sys`, `/dev`.
  `/data/local/tmp` remains writable when root is enabled.

Deleting the current folder is not offered; select its contents or go up first.

## Root access

Root is **off by default** and **resets when the manager restarts**.

- Enabling it asks for confirmation, then verifies `su -c id` reports `uid=0`.
- A yellow banner stays visible while it is on.
- With root enabled, reads and writes use `su -c`, so `/data`, `/system` and other protected-by-
  permissions paths are readable.
- The protected list above still applies to writes.
- If the root manager denies access, the operation fails with a clear error and nothing is changed.

## Safety

- Every operation is checked against the protected list and against the current recording state on
  the server, not just in the UI.
- Names and paths are validated and shell-quoted; there are no free-form shell commands.
- Mutations are appended to `reports/files/file-actions.jsonl` with the action, paths and root state.
- File management is not available in offline HTML reports.

## Troubleshooting

| Symptom | What to try |
|---|---|
| `no adb device` | Reconnect wireless ADB; see [device selection](CLI.md#device-selection). |
| `permission denied` | Enable **Root** for that path, or choose a folder under `/sdcard`. |
| `file operations are blocked while GXR Profiler is recording` | Stop the recording, then press **Refresh**. |
| A folder download is refused | Folders are not downloaded recursively; open the folder and select files. |
| Upload fails with a size error | The file is over 8 GB; use the Installer for large APK/OBB sets. |
| Root toggle turns itself off | Expected: root is per session and resets when the manager restarts. |
| Protected path is refused | That path is intentionally blocked from delete or replacement. |
