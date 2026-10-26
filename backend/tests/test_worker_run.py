import time
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


def test_port_drift_aborts_immediately(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    drift = tmp_path / "drift.py"
    drift.write_text(
        "import time\n"
        "print('=== round 1/1 (wipe) ===')\n"
        "print('  cold boot with -wipe-data ...')\n"
        "time.sleep(60)\n")
    cfg["script_path"] = str(drift)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setattr(worker.emulator, "device_booted", lambda *a, **k: False)
    monkeypatch.setattr(worker.emulator, "_emulator_serials",
                        lambda sdk: ["emulator-5556"])
    monkeypatch.setattr(worker.emulator, "device_present", lambda *a, **k: False)
    monkeypatch.setattr(worker, "BOOT_WATCH_INTERVAL", 0)
    db.init_db()
    run_id = db.create_run(url="u", rounds=3, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=str(drift), out_dir=str(tmp_path))
    started = time.time()
    worker.RunWorker(lambda: cfg).execute(run_id)
    elapsed = time.time() - started
    run = db.get_run(run_id)
    assert run["status"] == "failed"
    assert "emulator-5556" in (run["error"] or "")
    assert elapsed < 20
    assert [r["status"] for r in db.list_rounds(run_id)].count("skipped") == 2


def test_port_drift_ignored_while_serial_is_still_booting(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    booting = tmp_path / "booting.py"
    booting.write_text(
        "import time\n"
        "print('=== round 1/1 (wipe) ===')\n"
        "print('  cold boot with -wipe-data ...')\n"
        "time.sleep(3)\n")
    cfg["script_path"] = str(booting)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)
    monkeypatch.setattr(worker.emulator, "device_booted", lambda *a, **k: False)
    monkeypatch.setattr(worker.emulator, "_emulator_serials",
                        lambda sdk: ["emulator-5556"])
    monkeypatch.setattr(worker.emulator, "device_present",
                        lambda sdk, serial: serial == "emulator-5554")
    monkeypatch.setattr(worker, "BOOT_WATCH_INTERVAL", 0)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=str(booting), out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert db.get_run(run_id)["status"] == "succeeded"
    assert "port_drift" not in {e["kind"] for e in db.list_events(run_id)}


def test_cancel_during_emulator_boot_marks_canceled(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)

    def raise_canceled(*args, **kwargs):
        raise worker.emulator.EmulatorCanceled("canceled")

    monkeypatch.setattr(worker.emulator, "ensure_emulator", raise_canceled)
    monkeypatch.setattr(worker.emulator, "kill_emulator", lambda *a, **k: None)
    db.init_db()
    run_id = db.create_run(url="u", rounds=3, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert db.get_run(run_id)["status"] == "canceled"


def test_cancel_queued_run_marks_canceled_and_skips_execution(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    started = []
    monkeypatch.setattr(worker.emulator, "ensure_emulator",
                        lambda *a, **k: started.append(1))
    db.init_db()
    run_id = db.create_run(url="u", rounds=3, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    w = worker.RunWorker(lambda: cfg)

    assert w.cancel(run_id) is True
    assert db.get_run(run_id)["status"] == "canceled"

    w.execute(run_id)
    assert started == []
    assert db.get_run(run_id)["status"] == "canceled"


def test_execute_backs_off_when_run_canceled_after_precheck(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    started = []
    monkeypatch.setattr(worker.emulator, "ensure_emulator",
                        lambda *a, **k: started.append(1))
    db.init_db()
    run_id = db.create_run(url="u", rounds=3, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=cfg["script_path"], out_dir=str(tmp_path))
    stale = db.get_run(run_id)
    real_get_run = db.get_run
    w = worker.RunWorker(lambda: cfg)
    assert w.cancel(run_id) is True
    # 模拟竞态：execute 读到的是取消前的快照
    monkeypatch.setattr(worker.db, "get_run", lambda rid: stale)

    w.execute(run_id)

    assert started == []
    assert real_get_run(run_id)["status"] == "canceled"


def test_child_terminated_when_read_loop_raises(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    chatty = tmp_path / "chatty.py"
    marker = tmp_path / "still_alive.txt"
    chatty.write_text(
        "import time\n"
        "print('model: x', flush=True)\n"
        "time.sleep(6)\n"
        f"open({str(marker)!r}, 'w').write('alive')\n")
    cfg["script_path"] = str(chatty)
    monkeypatch.setattr(worker.emulator, "ensure_emulator", lambda *a, **k: None)

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(worker.db, "insert_log_line", boom)
    db.init_db()
    run_id = db.create_run(url="u", rounds=1, avd="AVD", serial="emulator-5554",
                           pkg="p", plan="wipe", sdk_root="/sdk",
                           script_path=str(chatty), out_dir=str(tmp_path))
    started = time.time()
    worker.RunWorker(lambda: cfg).execute(run_id)
    assert time.time() - started < 15
    time.sleep(8)
    assert not marker.exists(), "child process survived the failed read loop"
    run = db.get_run(run_id)
    assert run["status"] == "failed"
    assert "db down" in (run["error"] or "")