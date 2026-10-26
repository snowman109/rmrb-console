from fastapi.testclient import TestClient

from app import db
from app.main import app, worker as global_worker


def _client(monkeypatch):
    db.init_db()
    monkeypatch.setattr(global_worker, "submit", lambda url, rounds, avd: _fake_run())
    return TestClient(app)


def _fake_run():
    return db.create_run(url="u", rounds=2, avd="A", serial="emulator-5554",
                         pkg="p", plan="wipe", sdk_root="/s", script_path="/x",
                         out_dir="/tmp/x")


def test_create_run_validates_rounds(monkeypatch):
    c = _client(monkeypatch)
    assert c.post("/api/runs", json={"url": "https://x", "rounds": 0}).status_code == 422
    assert c.post("/api/runs", json={"url": "https://x", "rounds": 1001}).status_code == 422


def test_create_and_fetch_run(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/api/runs", json={"url": "https://x", "rounds": 2})
    assert r.status_code == 200
    run_id = r.json()["id"]
    detail = c.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["rounds"] == 2
    assert detail["counts"] == {}


def test_events_and_logs_incremental(monkeypatch):
    c = _client(monkeypatch)
    run_id = _fake_run()
    db.insert_event(run_id, 1, "click_ok", "True")
    db.insert_log_line(run_id, 1, "stdout", "hello")
    assert len(c.get(f"/api/runs/{run_id}/events?after_id=0").json()) == 1
    assert len(c.get(f"/api/runs/{run_id}/logs?after_seq=0").json()) == 1
    assert c.get(f"/api/runs/{run_id}/logs?after_seq=1").json() == []


def test_export_csv(monkeypatch):
    c = _client(monkeypatch)
    run_id = _fake_run()
    db.upsert_round(run_id, 1, {"status": "OK", "channel": "c"})
    body = c.get(f"/api/runs/{run_id}/export.csv").text
    assert body.startswith("round,action,")
    assert "OK" in body