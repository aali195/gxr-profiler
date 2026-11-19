# Soft-reboot and crash investigation reports

[Findings index](../../README.md#findings-index) | [Crash & soft-reboot logs](../../crash-logs.md)

Dated, sanitized investigations of unexpected headset restarts. Start with the log-format reference:
[crash, soft-reboot & error logs](../../crash-logs.md).

- [2026-11-17 - two Beat Saber soft reboots: SystemUI HWUI animation race](2026-11-17-systemui-hwui-beatsaber.md)
  - Two framework soft reboots while playing Beat Saber at 90 Hz on the thermal-modded headset.
  - Both are `com.android.systemui` native crashes in `libhwui` animation code, not thermal,
    root, kernel or power faults.
- [2026-10-18 to 2026-11-17 - historical tombstone sweep](2026-11-17-historical-tombstones.md)
  - All 15 retained tombstones: 12 SystemUI HWUI races, 2 perception head-tracking init failures,
    and 1 Immersive View XR Vulkan/foveation crash.
  - Confirms the SystemUI and perceptionhost signatures existed before the thermal mod.
