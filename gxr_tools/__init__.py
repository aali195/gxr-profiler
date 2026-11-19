"""GXR Tools: thermal profiler and device manager for Galaxy XR (SM-I610).

The suite contains two apps over a shared core:

- ``gxr_tools.profiler`` - read-only recording, runs, comparison and reports.
- ``gxr_tools.manager`` - diagnostics, package management and device settings.

Recording, preview and report export are read-only. Device changes only happen
through explicit GXR Manager actions.
"""

__version__ = "2.0.0"
