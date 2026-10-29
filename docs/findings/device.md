# Device identity, calibration & boundary

[Findings index](../README.md) | [Commands](../COMMANDS.md)

One-time snapshot written to `meta.json -> device_info` at recording start. Values below are from
the current SM-I610. Manufacture date, region, current IPD/calibration status and guardian state do
not require root; measured IPD, calibration file dates and the first-setup estimate do.

## Tests & results

Probed 2026-10-25 on SM-I610, build `UML2.260301.001.I610UEU2AZF3`.

| Probe | Observed result |
|---|---|
| `getprop ril.manufacturedate` | `20251201` -> **2025-12-01** |
| `getprop mdc.country_code`, `mdc.countryiso_code`, `ro.csc.sales_code`, `persist.sys.locale` | `UNITED KINGDOM`, `GB`, `TXV`, `en-GB` |
| `dumpsys cpm` / `IPD Data` | left/right 34.1515 mm -> **68.303 mm** in use |
| root `ipd.textproto` | **71.85291 mm** measured; created `2026-10-14T00:39:47Z` |
| root `stat` eye/face files | `2026-10-14T00:40:43Z` / `00:42:01Z` |
| root `stat settings_ssaid.xml`, `settings_secure.xml` | `2026-06-12 06:46:54` local -> **134 days** |
| secure/system boundary settings | consent `1`, toggle `0`, radius `1.0`, placement `0`, position `0`, floor `2`, offset `-1.0361316` |

## Findings

- Manufacture date comes from RIL, not `ro.build.date`.
- Region is **United Kingdom (GB)**, CSC **TXV**, locale `en-GB`.
- Measured IPD and in-use IPD are different values; do not conflate them.
- First setup is an estimate from user-settings file mtimes, not an authoritative reset date.
- Guardian state is split between secure and system settings; current guardian is off.
- Existing runs are not backfilled with these fields.

## Details

### Manufacture date
- `ril.manufacturedate` is exposed as `YYYYMMDD`; the current unit reports `20251201` ->
  **2025-12-01**.
- This is the RIL manufacturing date, not the firmware build date (`ro.build.date` is
  `2026-06-12` on this unit).

### Region and sales code
- Current unit: **United Kingdom (GB)**, CSC **TXV**, locale **en-GB**.
- Sources, in order:
  - country name: `mdc.country_code` (`UNITED KINGDOM`)
  - ISO country: `mdc.countryiso_code` (fallback `persist.sys.selected_country_iso`)
  - sales/CSC: `ro.csc.sales_code` (fallback `ro.boot.sales_code`)
  - locale: `persist.sys.locale` (fallback `ro.product.locale`)
- `mdc.country_code` is uppercase in the property and is title-cased for display. `TXV` is a
  Samsung CSC/sales code, not a language or locale.
- The UI shows `United Kingdom (GB) - CSC TXV`; Compare uses the shorter `GB - TXV`.

### IPD and eye/face calibration
- Measured IPD comes from `/data/vendor/openpx/calibration/records/ipd.textproto`
  (`ipd_mm`, `encoder_left_mm`, `encoder_right_mm`, `created_at`).
- Current measured IPD: **71.85 mm**; rendering/in-use IPD from CPM: **68.30 mm**.
- Eye calibration file: `/data/vendor/openpx/eye_tracking/eye_tracking_calibration.bin`
  (mtime `2026-10-14T00:40:43Z`). Face:
  `/data/vendor/openpx/face_tracking/face_tracking_calibration.pb`
  (mtime `2026-10-14T00:42:01Z`). IPD file mtime is `2026-10-14T00:39:47Z`.
- Without root, CPM `IPD Data` gives the current in-use IPD and system settings give the
  calibration-needed/status flags; measured IPD and file dates are missing.

### Approximate first setup
- The earliest mtime of `/data/system/users/0/settings_ssaid.xml` and
  `settings_secure.xml` is used as a **first user setup** estimate. Current unit:
  **2026-06-12 06:46:54 local**, 134 days before the 2026-10-25 recording session.
- These files are populated during initial setup after a reset, but their mtime is **not an
  authoritative reset timestamp** - restores or later writes can change it. The field is labeled
  **First setup (approx.)** and must not be presented as a reset date.
- Requires `--root`; runs recorded before this field existed show `--` and are not backfilled.

### Guardian / boundary
- Values come read-only from Android settings:
  - secure: `guardian_consent_granted`, `guardian_boundary_placement_mode`,
    `guardian_position_setup_available`, `guardian_toggle_radius_available`,
    `guardian_floor_height_setup_mode`, `guardian_floor_y_offset_from_head`
  - system: `guardian_radius`, `toggle_guardian`
- Current unit: consent granted, guardian **off**, radius **1.00 m**, placement mode `0`,
  position setup **unavailable**, floor setup mode `2`, floor offset **-1.04 m**, radius control
  available.
- Boundary data does not require root.
