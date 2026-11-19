"""Shared fake package-manager output for Apps tests."""

APP_LIST = """###PACKAGES
package:com.example.app uid:10123 versionCode:42
package:com.android.systemui uid:1000 versionCode:34
package:com.samsung.stock uid:1000 versionCode:7
###SYSTEM
package:com.android.systemui
package:com.samsung.stock
###THIRD
package:com.example.app
###DISABLED
package:com.samsung.stock
###ENABLED
package:com.example.app
package:com.android.systemui
###ALL
package:com.example.app
package:com.android.systemui
package:com.samsung.stock
package:com.removed.system
###PATH
package:/data/app/~~abc/com.example.app-1/base.apk=com.example.app
package:/system/priv-app/SystemUI/SystemUI.apk=com.android.systemui
package:/system/priv-app/SamsungStock/SamsungStock.apk=com.samsung.stock
package:/system/priv-app/Removed/Removed.apk=com.removed.system
###INSTALLER
package:com.example.app installer=com.android.vending
package:com.android.systemui
package:com.samsung.stock
package:com.removed.system
###CPUINFO
  12.5% 123/com.example.app: 10% user + 2.5% kernel
   3.0% 456/com.samsung.stock:remote: 1% user + 2% kernel
###PS
PID UID RSS NAME
123 10123 2048 com.example.app
456 1000 4096 com.samsung.stock:remote
###STAT
/proc/123/stat:123 (com.example.app) S 1 0 0 0 0 0 0 0 0 0 200 90 0 0 20 0 12 0 1001 0 0
/proc/456/stat:456 (com.samsung.stock:remote) S 1 0 0 0 0 0 0 0 0 0 300 60 0 0 20 0 8 0 1002 0 0
###OOM
/proc/123/oom_score_adj:905
/proc/456/oom_score_adj:200
###GPUMEM
Proc 123 total: 1048576
Proc 456 total: 2097152
"""

DETAIL = """Packages:
  Package [com.example.app] (abc):
    userId=10123
    codePath=/data/app/~~abc/com.example.app-1/base.apk
    versionCode=42 minSdk=30 targetSdk=34
    versionName=1.2.3
    flags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ALLOW_BACKUP ]
    dataDir=/data/user/0/com.example.app
    installerPackageName=com.android.vending
    firstInstallTime=2025-01-02 03:04:05
    lastUpdateTime=2025-02-03 04:05:06
    primaryCpuAbi=arm64-v8a
    requested permissions:
      android.permission.INTERNET
      android.permission.CAMERA
    install permissions:
    User 0: ceDataInode=123 installed=true hidden=false suspended=false stopped=false notLaunched=false enabled=0
"""
