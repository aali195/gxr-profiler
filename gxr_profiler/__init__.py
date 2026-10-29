"""gxr_profiler - read-only thermal/performance profiler for Galaxy XR (SM-I610).

Collects over wireless ADB using only read-only commands: a logcat stream plus a
1 Hz poll. Includes a CLI, a static report, and a local web app (viewer +
recorder). Nothing is ever written to the headset.
"""

__version__ = "0.3.0"
