from pathlib import Path

from app import db, worker


def _cfg(tmp_path):
    return {
        "sdk_root": "/sdk",
        "script_path": str(Path(__file__).parent / "fixtures" / "fake_avd_rounds.py"),
        "default_url": "https://x", "default_avd": "AVD", "default_rounds": 5,
    }


def test_abort_after_three_environment_failures(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_STATUS", "BOOT_FAIL")
    db.init_db()
    run_id = db.create_run(url="u", rounds=5, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    run = db.get_run(run_id)
    assert run["status"] == "failed"
    assert "BOOT_FAIL" in (run["error"] or "")
    assert [r["status"] for r in db.list_rounds(run_id)].count("skipped") == 2


def test_open_fail_does_not_trigger_abort(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_STATUS", "OPEN_FAIL")
    db.init_db()
    run_id = db.create_run(url="u", rounds=5, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert db.get_run(run_id)["status"] == "succeeded"
    assert len(db.list_rounds(run_id)) == 5


def test_cancel_terminates_and_marks_canceled(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setenv("FAKE_SLEEP", "30")
    db.init_db()
    run_id = db.create_run(url="u", rounds=3, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    w = worker.RunWorker(lambda: cfg)
    import threading
    t = threading.Thread(target=w.execute, args=(run_id,))
    t.start()
    import time; time.sleep(1)
    assert w.cancel(run_id) is True
    t.join(timeout=15)
    assert db.get_run(run_id)["status"] == "canceled"