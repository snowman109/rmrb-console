import subprocess
import threading

import pytest

from app import emulator


def test_emulator_port_parses_serial():
    assert emulator.emulator_port("emulator-5554") == 5554
    assert emulator.emulator_port("emulator-5556") == 5556
    assert emulator.emulator_port("R58M12345") is None


def test_adb_bin_prefers_sdk_root(tmp_path):
    adb = tmp_path / "platform-tools" / "adb"
    adb.parent.mkdir(parents=True)
    adb.write_text("#!/bin/sh\n")
    adb.chmod(0o755)
    assert emulator.adb_bin(str(tmp_path)) == str(adb)


def test_ensure_emulator_reports_port_mismatch(monkeypatch):
    monkeypatch.setattr(emulator, "list_devices", lambda sdk: ["emulator-5556"])
    monkeypatch.setattr(emulator, "device_booted", lambda sdk, serial: False)
    with pytest.raises(RuntimeError, match="emulator-5556"):
        emulator.ensure_emulator("/sdk", "AVD", "emulator-5554", timeout=1)


def test_device_present_counts_offline_entries(monkeypatch):
    output = "List of devices attached\nemulator-5554\toffline\nemulator-5556\tdevice\n"
    monkeypatch.setattr(emulator, "adb_bin", lambda sdk: "/sdk/platform-tools/adb")
    monkeypatch.setattr(emulator, "_run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, output, ""))
    assert emulator.list_devices("/sdk") == ["emulator-5556"]
    assert emulator.device_present("/sdk", "emulator-5554") is True
    assert emulator.device_present("/sdk", "emulator-5558") is False


def test_kill_emulator_falls_back_to_pkill_when_process_survives(monkeypatch):
    launched = []
    monkeypatch.setattr(emulator, "adb_bin", lambda sdk: "/sdk/platform-tools/adb")
    monkeypatch.setattr(emulator, "_run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 1, "", "error: no emulator"))
    monkeypatch.setattr(emulator, "_emulator_process_alive", lambda avd: True)
    monkeypatch.setattr(emulator.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(emulator.subprocess, "run",
                        lambda cmd, **k: launched.append(cmd) or subprocess.CompletedProcess(
                            cmd, 0, "", ""))

    emulator.kill_emulator("/sdk", "emulator-5554", "AVD")

    assert any(cmd[0] == "pkill" and "-avd AVD" in cmd for cmd in launched)


def test_kill_emulator_skips_pkill_when_process_gone(monkeypatch):
    launched = []
    monkeypatch.setattr(emulator, "adb_bin", lambda sdk: "/sdk/platform-tools/adb")
    monkeypatch.setattr(emulator, "_run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, "", ""))
    monkeypatch.setattr(emulator, "_emulator_process_alive", lambda avd: False)
    monkeypatch.setattr(emulator.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(emulator.subprocess, "run",
                        lambda cmd, **k: launched.append(cmd) or subprocess.CompletedProcess(
                            cmd, 0, "", ""))

    emulator.kill_emulator("/sdk", "emulator-5554", "AVD")

    assert launched == []


def test_ensure_emulator_honors_cancel_event(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(emulator, "device_booted", lambda sdk, serial: False)
    monkeypatch.setattr(emulator, "list_devices", lambda sdk: ["emulator-5554"])

    with pytest.raises(emulator.EmulatorCanceled):
        emulator.ensure_emulator("/sdk", "AVD", "emulator-5554", timeout=1,
                                 cancel_event=cancel)