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