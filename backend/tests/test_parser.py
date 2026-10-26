import pytest

from app.parser import (Event, import_csv, is_environment_failure,
                        parse_line, parse_run_meta)


@pytest.mark.parametrize("line,kind", [
    ("=== round 1/1 (wipe) ===", "round_start"),
    ("  cold boot with -wipe-data ...", "cold_boot"),
    ("  android_id: aaa -> bbb", "android_id"),
    ("    chrome tap: 仍然下载", "chrome_tap"),
    ("    setup tap: Start", "setup_tap"),
    ("    app tap: 同意", "app_tap"),
    ("  click ok: True apk: https://x/a.apk", "click_ok"),
    ("  click ok: False apk: ", "click_fail"),
    ("  host download ok: 81587534 bytes", "host_download_ok"),
    ("  host download failed, fallback to Chrome UI", "host_download_fail"),
    ("   install attempt 1 : Failure", "install_attempt"),
    ("  channel: wdb-ltt | status: OK", "channel_status"),
])
def test_parse_line_kinds(line, kind):
    ev = parse_line(line)
    assert isinstance(ev, Event)
    assert ev.kind == kind


def test_parse_line_ignores_unknown():
    assert parse_line("some random output") is None


def test_channel_status_message_has_both_parts():
    ev = parse_line("  channel: (none) | status: OPEN_FAIL")
    assert ev.message == "(none) | OPEN_FAIL"


@pytest.mark.parametrize("line,expected", [
    ("model: sdk_gphone64_arm64", ("model", "sdk_gphone64_arm64")),
    ("qemu: 1", ("qemu", "1")),
])
def test_parse_run_meta(line, expected):
    assert parse_run_meta(line) == expected


@pytest.mark.parametrize("status,expected", [
    ("BOOT_FAIL", True), ("NO_PAGE", True), ("NO_APK", True),
    ("CLICK_FAIL:x", True), ("INSTALL_FAIL", True), ("CSV_MISSING", True),
    ("OPEN_FAIL", False), ("OPEN_NO_CHANNEL", False), ("OK", False),
])
def test_is_environment_failure(status, expected):
    assert is_environment_failure(status) is expected


def test_import_csv_maps_columns(tmp_path):
    p = tmp_path / "round_1.csv"
    p.write_text(
        "round,reset,android_id_before,android_id_after,public_ip,clicked_at,"
        "click_url,apk_url,install_at,open_at,installer,first_install,"
        "openinstall_channel,app_version,status,log_excerpt,apk_src\n"
        "1,wipe,a,b,1.2.3.4,2026-10-26 10:00,cu,au,ia,oa,null,2026-10-26,"
        "wdb-ltt,2.7.1,OK,\"line1\nline2\",click\n",
        encoding="utf-8")
    row = import_csv(p)
    assert row["action"] == "wipe"
    assert row["channel"] == "wdb-ltt"
    assert row["log_excerpt"] == "line1\nline2"
    assert row["status"] == "OK"