"""gxr_profiler - thermal/performance profiler for Galaxy XR (SM-I610).

Collects over wireless ADB using read-only commands: a logcat stream plus a
1 Hz poll. Includes a CLI, a static report, and a local web app (viewer +
recorder). Recording, diagnostics and export are read-only; the optional
Tools > Apps workflow can change package state only after explicit user
confirmation.
"""

__version__ = "0.3.0"
