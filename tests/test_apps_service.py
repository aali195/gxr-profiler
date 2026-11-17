import json
from types import SimpleNamespace

from gxr_profiler.core.apps import PACKAGE_FALLBACK_SCRIPT
from gxr_profiler.server.apps import AppsService

APP_LIST = """###USERS
Users:
    UserInfo{0:Owner:c13} running
###PACKAGES
package:com.example.app uid:10123 versionCode:42
package:com.android.systemui uid:1000 versionCode:34
###SYSTEM
package:com.android.systemui
###THIRD
package:com.example.app
###DISABLED
###ENABLED
package:com.example.app
package:com.android.systemui
###ALL
package:com.example.app
package:com.android.systemui
###PATH
package:/data/app/~~abc/com.example.app-1/base.apk=com.example.app
package:/system/priv-app/SystemUI/SystemUI.apk=com.android.systemui
###INSTALLER
package:com.example.app installer=com.android.vending
package:com.android.systemui
###CPUINFO
  12.5% 321/com.example.app: 10% user + 2.5% kernel
###PS
PID UID RSS NAME
321 10123 2048 com.example.app
###STAT
/proc/321/stat:321 (com.example.app) S 1 0 0 0 0 0 0 0 0 0 200 90 0 0 20 0 12 0 1001 0 0
###OOM
/proc/321/oom_score_adj:905
###GPUMEM
Proc 321 total: 1048576
"""

DETAIL = """Packages:
  Package [com.example.app] (abc):
    codePath=/data/app/~~abc/com.example.app-1/base.apk
    versionCode=42 minSdk=30 targetSdk=34
    versionName=1.2.3
    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ]
    dataDir=/data/user/0/com.example.app
    installerPackageName=com.android.vending
    firstInstallTime=2025-01-02 03:04:05
    lastUpdateTime=2025-02-03 04:05:06
    User 0: installed=true hidden=false suspended=false stopped=false enabled=0
"""


class FakeAppsAdb:
    def __init__(self, list_text=APP_LIST, detail_text=DETAIL, fail_action=False):
        self.list_text = list_text
        self.detail_text = detail_text
        self.fail_action = fail_action
        self.shell_calls = []
        self.run_calls = []

    def shell(self, script, timeout=25.0):
        self.shell_calls.append(script)
        if "###USERS" in script:
            return self.list_text
        if script == PACKAGE_FALLBACK_SCRIPT:
            return "package:com.example.app uid:10123\n"
        if script.startswith("du -sk"):
            return "1024 /data/app/~~abc/com.example.app-1\n512 /system/priv-app/SystemUI/SystemUI.apk\n"
        if script.startswith("dumpsys package"):
            return self.detail_text
        if script.startswith("pm path"):
            return "package:/data/app/~~abc/com.example.app-1/base.apk\n"
        if script == "su -c id":
            return "uid=0(root) gid=0(root) context=u:r:ksu:s0\n"
        if script.startswith("su -c") and "du -sk" in script:
            return "100 /data/user/0/com.example.app\n8 /data/user/0/com.example.app/cache\n"
        return ""

    def run(self, args, timeout=25.0):
        self.run_calls.append(args)
        if self.fail_action:
            return SimpleNamespace(stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]", stderr="", returncode=1)
        return SimpleNamespace(stdout="Success", stderr="", returncode=0)


def _service(tmp_path, adb):
    return AppsService(serial="fake", reports_dir=str(tmp_path / "reports"), adb_factory=lambda serial=None: adb)


def test_apps_service_lists_and_reads_detail(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    data = service.list_packages()
    assert data["summary"]["total"] == 2
    assert data["summary"]["size_kb"] == 1536
    assert data["users"] == [0]
    row = next(item for item in data["packages"] if item["package"] == "com.example.app")
    assert row["kind"] == "user"
    assert row["actions"] == ["disable", "uninstall"]
    assert row["proc_count"] == 1
    assert row["cpu_pct"] == 12.5
    assert row["rss_kb"] == 2048
    assert row["gpu_mem_kb"] == 1024
    assert row["size_kb"] == 1024
    assert row["threads"] == 12
    assert row["oom_class"] == "cached"

    detail = service.detail("com.example.app", root=True)
    assert detail["detail"]["version_name"] == "1.2.3"
    assert detail["detail"]["apk_paths"] == ["/data/app/~~abc/com.example.app-1/base.apk"]
    assert detail["root"]["available"] is True
    assert detail["root"]["data_kb"] == 100
    assert detail["root"]["cache_kb"] == 8


def test_apps_service_action_validates_and_logs(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    result = service.run_action("com.example.app", "disable", confirm=True)
    assert result["ok"] is True
    assert result["command"] == "pm disable-user --user 0 com.example.app"
    assert adb.run_calls[-1][-1] == "pm disable-user --user 0 com.example.app"
    log_path = tmp_path / "reports" / "app-actions.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["package"] == "com.example.app"
    assert entry["action"] == "disable"


def test_apps_service_rejects_unavailable_and_critical_actions(tmp_path):
    adb = FakeAppsAdb()
    service = _service(tmp_path, adb)
    try:
        service.run_action("com.example.app", "enable", confirm=True)
    except ValueError:
        pass
    else:
        raise AssertionError("enable should be unavailable for an enabled package")

    try:
        service.run_action("com.android.systemui", "disable", confirm=True)
    except PermissionError as exc:
        assert "cannot be disabled or removed" in str(exc)
    else:
        raise AssertionError("critical package should not be disableable")

    try:
        service.run_action("com.example.app", "disable", confirm=False)
    except ValueError:
        pass
    else:
        raise AssertionError("confirmation should be required")


def test_apps_service_failure_result_and_fallback(tmp_path):
    adb = FakeAppsAdb(list_text="###PACKAGES\nError: Unknown option\n", fail_action=True)
    service = _service(tmp_path, adb)
    data = service.list_packages()
    assert data["packages"][0]["package"] == "com.example.app"
    result = service.run_action("com.example.app", "disable", confirm=True)
    assert result["ok"] is False
    assert "Failure" in result["output"]
