# Soft-reboot and crash investigation reports

Dated, sanitized investigations of unexpected headset restarts. Start with the log-format reference:
[crash, soft-reboot & error logs](../../crash-logs.md).

- [2026-11-17 - two Beat Saber soft reboots: SystemUI HWUI animation race](2026-11-17-systemui-hwui-beatsaber.md)
  - Two framework soft reboots while playing Beat Saber at 90 Hz on the thermal-modded headset.
  - Both are `com.android.systemui` native crashes in `libhwui` animation code, not thermal,
    root, kernel or power faults.
