import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

ENV_FAILURE_STATUSES = {
    "BOOT_FAIL", "NO_PAGE", "NO_APK", "CLICK_FAIL", "INSTALL_FAIL", "CSV_MISSING",
}

CSV_COLUMNS = [
    "action", "android_id_before", "android_id_after", "public_ip",
    "clicked_at", "click_url", "apk_url", "install_at", "open_at",
    "installer", "first_install", "channel", "app_version", "status",
    "log_excerpt", "apk_src",
]

CSV_RENAME = {"reset": "action", "openinstall_channel": "channel"}


@dataclass
class Event:
    kind: str
    message: str


_ROUND_START = re.compile(r"^=== round (\d+)/(\d+) \((\w+)\) ===")
_ANDROID_ID = re.compile(r"^\s+android_id: (\S+) -> (\S+)")
_COLD_BOOT = re.compile(r"^\s+cold boot with -wipe-data")
_CLICK = re.compile(r"^\s+click ok: (\w+) apk: (.*)")
_HOST_DL_OK = re.compile(r"^\s+host download ok: (\d+) bytes")
_HOST_DL_FAIL = re.compile(r"^\s+host download failed")
_INSTALL = re.compile(r"^\s+install attempt (\d+) : (.*)")
_TAP = re.compile(r"^\s+(chrome|setup|app) tap: (.*)")
_CHANNEL = re.compile(r"^\s+channel: (.*) \| status: (\w+)")

_RUN_META = {
    "model": re.compile(r"^model: (.*)"),
    "qemu": re.compile(r"^qemu: (.*)"),
    "plan": re.compile(r"^plan: (.*)"),
}


def parse_line(line: str) -> Optional[Event]:
    m = _ROUND_START.match(line)
    if m:
        return Event("round_start", f"{m.group(1)}/{m.group(2)} ({m.group(3)})")

    m = _ANDROID_ID.match(line)
    if m:
        return Event("android_id", f"{m.group(1)} -> {m.group(2)}")

    if _COLD_BOOT.match(line):
        return Event("cold_boot", line.strip())

    m = _CLICK.match(line)
    if m:
        kind = "click_ok" if m.group(1).lower() == "true" else "click_fail"
        return Event(kind, f"{m.group(1)} apk: {m.group(2)}")

    m = _HOST_DL_OK.match(line)
    if m:
        return Event("host_download_ok", m.group(1))

    if _HOST_DL_FAIL.match(line):
        return Event("host_download_fail", line.strip())

    m = _INSTALL.match(line)
    if m:
        return Event("install_attempt", f"{m.group(1)}: {m.group(2)}")

    m = _TAP.match(line)
    if m:
        return Event(f"{m.group(1)}_tap", m.group(2))

    m = _CHANNEL.match(line)
    if m:
        return Event("channel_status", f"{m.group(1)} | {m.group(2)}")

    return None


def parse_run_meta(line: str) -> Optional[Tuple[str, str]]:
    for name, pattern in _RUN_META.items():
        m = pattern.match(line)
        if m:
            return name, m.group(1).strip()
    return None


def is_environment_failure(status: str) -> bool:
    if not status:
        return False
    return status.split(":", 1)[0].strip() in ENV_FAILURE_STATUSES


def import_csv(path: Path) -> Optional[dict]:
    path = Path(path)
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        row = next(reader, None)
    if row is None:
        return None

    result: Dict[str, Optional[str]] = {name: None for name in CSV_COLUMNS}
    for raw_name, value in row.items():
        if raw_name is None:
            continue
        name = CSV_RENAME.get(raw_name, raw_name)
        if name in result:
            result[name] = value
    return result