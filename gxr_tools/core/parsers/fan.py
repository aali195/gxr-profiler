"""Root-only fan telemetry."""

from __future__ import annotations

import re

FAN_PWM_RE = re.compile(r"pwm=(\d+)")
FAN_RPM1_RE = re.compile(r"rpm1=(\d+)")
FAN_RPM2_RE = re.compile(r"rpm2=(\d+)")


def parse_fan_root(lines: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    nums: list[float] = []
    for ln in lines:
        if "rpm1=" in ln or "pwm=" in ln:
            m = FAN_RPM1_RE.search(ln)
            if m:
                out["fan_rpm"] = float(m.group(1))
            m = FAN_RPM2_RE.search(ln)
            if m:
                out["fan_rpm2"] = float(m.group(1))
            m = FAN_PWM_RE.search(ln)
            if m:
                out["fan_pwm"] = float(m.group(1))
        else:
            try:
                nums.append(float(ln))
            except ValueError:
                pass
    if "fan_rpm" not in out and nums:
        out["fan_rpm"] = nums[0]
    if "fan_rpm2" not in out and len(nums) >= 2:
        out["fan_rpm2"] = nums[1]
    return out
