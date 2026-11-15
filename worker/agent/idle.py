"""마지막 키보드·마우스 입력 뒤 지난 시간 측정.

"남는 자원만 쓴다"를 판단하려면 사용률뿐 아니라 사람이 기기를 쓰고 있는지도 봐야 한다.
측정할 수 없는 환경(서버용 Linux, 컨테이너 등)에서는 None을 돌려주고, 서버는 이 판단을 건너뛴다.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess


def _windows() -> float | None:
    import ctypes

    class LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    # GetTickCount는 49.7일마다 0으로 돌아가므로 32비트 범위에서 뺀다
    elapsed = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return elapsed / 1000


def parse_ioreg(output: str) -> float | None:
    """`ioreg -c IOHIDSystem` 출력의 HIDIdleTime(나노초)을 초로 바꾼다."""
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', output)
    return int(match.group(1)) / 1_000_000_000 if match else None


def _macos() -> float | None:
    result = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=3)
    return parse_ioreg(result.stdout)


def _linux() -> float | None:
    if not shutil.which("xprintidle"):
        return None
    result = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=3)
    return int(result.stdout.strip()) / 1000


def user_idle_seconds() -> float | None:
    """마지막 입력 뒤 지난 초. 알 수 없으면 None."""
    system = platform.system()
    try:
        if system == "Windows":
            value = _windows()
        elif system == "Darwin":
            value = _macos()
        else:
            value = _linux()
    except Exception:
        return None
    return round(value, 1) if value is not None and value >= 0 else None
