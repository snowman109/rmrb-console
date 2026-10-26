import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from app.config import data_dir

_PORT_RE = re.compile(r"^emulator-(\d+)$")


def adb_bin(sdk_root: str) -> str:
    candidate = Path(sdk_root) / "platform-tools" / "adb"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("adb")
    if found:
        return found
    raise RuntimeError(f"adb not found under {sdk_root} or PATH")


def _emulator_bin(sdk_root: str) -> str:
    candidate = Path(sdk_root) / "emulator" / "emulator"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("emulator")
    if found:
        return found
    raise RuntimeError(f"emulator binary not found under {sdk_root} or PATH")


def _run(cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def list_devices(sdk_root: str) -> List[str]:
    try:
        out = _run([adb_bin(sdk_root), "devices"]).stdout
    except (RuntimeError, subprocess.SubprocessError, OSError):
        return []
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def device_booted(sdk_root: str, serial: str) -> bool:
    try:
        out = _run([adb_bin(sdk_root), "-s", serial, "shell",
                    "getprop", "sys.boot_completed"]).stdout
    except (RuntimeError, subprocess.SubprocessError, OSError):
        return False
    return out.strip() == "1"


def emulator_port(serial: str) -> Optional[int]:
    m = _PORT_RE.match(serial)
    return int(m.group(1)) if m else None


def _emulator_serials(sdk_root: str) -> List[str]:
    return [d for d in list_devices(sdk_root) if _PORT_RE.match(d)]


def ensure_emulator(sdk_root: str, avd: str, serial: str,
                    timeout: int = 480) -> None:
    if device_booted(sdk_root, serial):
        return

    others = _emulator_serials(sdk_root)
    if serial not in others and others:
        raise RuntimeError(f"expected {serial}, found {others[0]}")

    port = emulator_port(serial)
    if port is None:
        raise RuntimeError(f"expected emulator-<port> serial, got {serial}")

    log_path = data_dir() / "emulator_boot.log"
    with log_path.open("ab") as log:
        subprocess.Popen(
            [_emulator_bin(sdk_root), "-avd", avd, "-port", str(port),
             "-no-snapshot", "-no-audio", "-gpu", "auto",
             "-dns-server", "223.5.5.5,119.29.29.29"],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

    deadline = time.time() + timeout
    while time.time() < deadline:
        if device_booted(sdk_root, serial):
            return
        others = _emulator_serials(sdk_root)
        if serial not in others and others:
            raise RuntimeError(f"expected {serial}, found {others[0]}")
        time.sleep(3)
    raise RuntimeError(f"emulator {serial} did not boot within {timeout}s")


def kill_emulator(sdk_root: str, serial: str, avd: str) -> None:
    adb = adb_bin(sdk_root)
    for attempt in range(2):
        try:
            _run([adb, "-s", serial, "emu", "kill"], timeout=15)
        except (RuntimeError, subprocess.SubprocessError, OSError):
            pass
        time.sleep(2)
        if serial not in list_devices(sdk_root):
            return
    try:
        subprocess.run(["pkill", "-f", "--", f"-avd {avd}"], timeout=15)
    except (subprocess.SubprocessError, OSError):
        pass