import os
from pathlib import Path

from app import db, worker


def _cfg(tmp_path, status="OK"):
    script = Path(__file__).parent / "fixtures" / "fake_avd_rounds.py"
    return {
        "sdk_root": "/sdk", "script_path": str(script),
        "default_url": "https://x/?channelCode=c", "default_avd": "AVD",
        "default_rounds": 1,
    }, status


def test_run_round_records_csv_and_events(tmp_path, monkeypatch):
    cfg, status = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_STATUS", status)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    w = worker.RunWorker(config_provider=lambda: cfg)
    w.execute(run_id)

    rounds = db.list_rounds(run_id)
    assert len(rounds) == 1
    assert rounds[0]["status"] == "OK"
    assert rounds[0]["channel"] == "wdb-ltt"
    assert rounds[0]["android_id_after"] == "after456"
    assert db.get_run(run_id)["status"] == "succeeded"
    kinds = {e["kind"] for e in db.list_events(run_id)}
    assert {"round_start", "click_ok", "channel_status"} <= kinds
    logs = db.list_log_lines(run_id)
    assert logs[0]["line"] == "model: sdk_gphone64_arm64"
    assert len(logs) >= 10


def test_round_without_csv_is_partial(tmp_path, monkeypatch):
    cfg, _ = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    # 让假脚本在写 CSV 前崩溃
    broken = tmp_path / "broken.py"
    broken.write_text("print('=== round 1/1 (wipe) ==='); raise SystemExit(2)")
    cfg["script_path"] = str(broken)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=str(broken), out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    rows = db.list_rounds(run_id)
    assert rows[0]["status"] == "CSV_MISSING"
    assert rows[0]["source"] == "stdout"


def test_script_plan_banner_does_not_overwrite_run_plan(tmp_path, monkeypatch):
    cfg, _ = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert db.get_run(run_id)["plan"] == "wipe"


def test_apk_metadata_snapshotted_before_next_round(tmp_path, monkeypatch):
    cfg, _ = _cfg(tmp_path)
    apk = tmp_path / "round1.apk"
    monkeypatch.setattr(worker, "APK_PATH", str(apk))
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_APK", str(apk))
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    arts = db.list_apk_artifacts(run_id)
    assert len(arts) == 1
    assert arts[0]["size"] == 1024
    assert len(arts[0]["sha256"]) == 64


def test_stale_apk_from_previous_run_is_not_attributed(tmp_path, monkeypatch):
    cfg, _ = _cfg(tmp_path)
    apk = tmp_path / "round1.apk"
    apk.write_bytes(b"x" * 1024)
    monkeypatch.setattr(worker, "APK_PATH", str(apk))
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert db.list_apk_artifacts(run_id) == []


def test_failed_round_synthesizes_early_exit_event(tmp_path, monkeypatch):
    cfg, _ = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_STATUS", "NO_PAGE")
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    kinds = {e["kind"] for e in db.list_events(run_id)}
    assert "no_page" in kinds