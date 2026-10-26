from app.db import (create_run, get_run, init_db, list_rounds,
                    mark_interrupted_runs, update_run, upsert_round)


def _new_run(**over):
    kwargs = dict(url="u", rounds=3, avd="A", serial="emulator-5554", pkg="p",
                  plan="wipe", sdk_root="/sdk", script_path="/s.py", out_dir="/tmp/1")
    kwargs.update(over)
    return create_run(**kwargs)


def test_create_and_get_run():
    init_db()
    run_id = _new_run()
    run = get_run(run_id)
    assert run["status"] == "queued"
    assert run["rounds"] == 3


def test_upsert_round_is_idempotent():
    init_db()
    run_id = _new_run()
    upsert_round(run_id, 1, {"status": "OK", "channel": "c"})
    upsert_round(run_id, 1, {"status": "OPEN_FAIL", "channel": ""})
    rows = list_rounds(run_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "OPEN_FAIL"


def test_mark_interrupted_runs():
    init_db()
    run_id = _new_run()
    update_run(run_id, status="running")
    assert mark_interrupted_runs() == 1
    assert get_run(run_id)["status"] == "interrupted"