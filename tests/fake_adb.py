"""A minimal in-memory AdbClient for tests."""

from __future__ import annotations

import subprocess
import types

POLL_RESPONSE = """###FREQ
1382400
1382400
691200
691200
691200
691200
###PMAX
2361600
2361600
###GCLK
421
###GBUSY
35 %
###GBUSYN
350000 1000000
###GTMP
60000
###GTHR
0
###SEC
300
310
305
###LOAD
1.0 1.0 1.0 1/100 123
###MEM
MemAvailable: 7000000 kB
MemFree: 2000000 kB
SwapFree: 3000000 kB
###BATT
  AC powered: true
  status: 2
  level: 80
  temperature: 280
###WIFI
WifiInfo: SSID: "Test", BSSID: ca:75:0c:bd:f8:06, IP: /10.0.0.2, Security type: 4, Wi-Fi standard: 8, RSSI: -44, Link speed: 3843Mbps, Tx Link speed: 3843Mbps, Max Supported Tx Link speed: 5764Mbps, Rx Link speed: 4803Mbps, Max Supported Rx Link speed: 5764Mbps, Frequency: 6295MHz
###THERM
Cached temperatures:
Temperature{mValue=0.0, mType=2, mName=BAT, mStatus=0}
Current temperatures from HAL:
Temperature{mValue=37.8, mType=0, mName=CPU5, mStatus=0}
Temperature{mValue=36.4, mType=1, mName=GPU0, mStatus=0}
Temperature{mValue=33.0, mType=12, mName=WIFI, mStatus=0}
Temperature{mValue=32.5, mType=13, mName=AP, mStatus=0}
Current cooling devices from HAL:
###END
"""

PROPS = """[ro.product.model]: [SM-I610]
[ro.product.device]: [xrvst2]
[ro.product.name]: [xrvst2ue]
[ro.board.platform]: [anorak]
[ro.soc.model]: [SXR2230P]
[ro.build.version.release]: [14]
[ro.build.version.sdk]: [34]
[ro.build.display.id]: [UML2.260101.001.I610XXU1AAAA]
[ro.build.fingerprint]: [samsung/xrvst2ue/xrvst2:14/UML2.260101.001/I610XXU1AAAA:user/release-keys]
"""


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = self
        self._done = False

    def readline(self) -> str:
        return ""

    def terminate(self) -> None:
        pass


class FakeAdb:
    def __init__(
        self,
        poll_response: str = POLL_RESPONSE,
        props: str = PROPS,
        media_response: str = "",
        process_response: str = "",
        process_io_response: str = "",
        package_response: str = "",
    ) -> None:
        self.poll_response = poll_response
        self.props = props
        self.media_response = media_response
        self.process_response = process_response
        self.process_io_response = process_io_response
        self.package_response = package_response
        self.shell_calls: list[str] = []

    def shell(self, script: str, timeout: float = 25.0) -> str:
        self.shell_calls.append(script)
        if "###FREQ" in script:
            return self.poll_response
        if "###MEDIA" in script:
            return self.media_response
        if "###PKGS" in script:
            return self.package_response
        if "###CPUINFO" in script:
            return self.process_response
        if "###IO" in script:
            return self.process_io_response
        if script.startswith("date"):
            return "10-17 03:00:00"
        if "settings get global low_power" in script:
            return "0"
        if "IPerceptionLifecycleManager" in script:
            return "service_id=65537(HeadTracking)\n      friendly_name=HandJoints_HeadTracking\n"
        return ""

    def run(self, args: list[str], timeout: float = 25.0) -> subprocess.CompletedProcess:
        stdout = self.props if args[-1] == "getprop" else ""
        return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    def popen(self, args: list[str]):
        return _FakeProc()
