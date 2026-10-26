import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import db_path

RUN_COLUMNS = {
    "url", "rounds", "avd", "serial", "pkg", "plan", "status", "exit_code",
    "error", "sdk_root", "script_path", "model", "qemu", "out_dir",
    "started_at", "finished_at",
}

ROUND_COLUMNS = {
    "action", "android_id_before", "android_id_after", "public_ip",
    "clicked_at", "click_url", "apk_url", "install_at", "open_at",
    "installer", "first_install", "channel", "app_version", "status",
    "apk_src", "log_excerpt", "source",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    rounds INTEGER NOT NULL,
    avd TEXT,
    serial TEXT,
    pkg TEXT,
    plan TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    exit_code INTEGER,
    error TEXT,
    sdk_root TEXT,
    script_path TEXT,
    model TEXT,
    qemu TEXT,
    out_dir TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    round_no INTEGER NOT NULL,
    action TEXT,
    android_id_before TEXT,
    android_id_after TEXT,
    public_ip TEXT,
    clicked_at TEXT,
    click_url TEXT,
    apk_url TEXT,
    install_at TEXT,
    open_at TEXT,
    installer TEXT,
    first_install TEXT,
    channel TEXT,
    app_version TEXT,
    status TEXT,
    apk_src TEXT,
    log_excerpt TEXT,
    source TEXT,
    UNIQUE(run_id, round_no)
);

CREATE TABLE IF NOT EXISTS round_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    round_no INTEGER,
    ts TEXT,
    kind TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS log_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    ts TEXT,
    stream TEXT,
    line TEXT
);

CREATE TABLE IF NOT EXISTS apk_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    round_no INTEGER,
    path TEXT,
    size INTEGER,
    mtime TEXT,
    sha256 TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS emulator_log_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    ts TEXT,
    line TEXT
);

CREATE INDEX IF NOT EXISTS idx_rounds_run_round ON rounds(run_id, round_no);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON round_events(run_id, id);
CREATE INDEX IF NOT EXISTS idx_logs_run_seq ON log_lines(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_emulogs_run_seq ON emulator_log_lines(run_id, seq);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def create_run(url: str, rounds: int, avd: str, serial: str, pkg: str,
               plan: str, sdk_root: str, script_path: str,
               out_dir: str) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """INSERT INTO runs (url, rounds, avd, serial, pkg, plan, sdk_root,
                                 script_path, out_dir, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)""",
            (url, rounds, avd, serial, pkg, plan, sdk_root, script_path,
             out_dir, now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_run(run_id: int, **fields: Any) -> None:
    unknown = set(fields) - RUN_COLUMNS
    if unknown:
        raise ValueError(f"unknown run fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    conn = connect()
    try:
        conn.execute(f"UPDATE runs SET {assignments} WHERE id = ?",
                     (*fields.values(), run_id))
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: int) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_runs(limit: int = 50, offset: int = 0) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_interrupted_runs() -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE runs SET status = 'interrupted', finished_at = ? WHERE status = 'running'",
            (now_iso(),),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def insert_log_line(run_id: int, seq: int, stream: str, line: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO log_lines (run_id, seq, ts, stream, line) VALUES (?, ?, ?, ?, ?)",
            (run_id, seq, now_iso(), stream, line),
        )
        conn.commit()
    finally:
        conn.close()


def list_log_lines(run_id: int, after_seq: int = -1) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM log_lines WHERE run_id = ? AND seq > ? ORDER BY seq",
            (run_id, after_seq),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_event(run_id: int, round_no: Optional[int], kind: str, message: str) -> None:
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO round_events (run_id, round_no, ts, kind, message)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, round_no, now_iso(), kind, message),
        )
        conn.commit()
    finally:
        conn.close()


def list_events(run_id: int) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM round_events WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_round(run_id: int, round_no: int, data: Dict[str, Any]) -> None:
    unknown = set(data) - ROUND_COLUMNS
    if unknown:
        raise ValueError(f"unknown round fields: {sorted(unknown)}")
    columns = ["run_id", "round_no"] + list(data)
    values = [run_id, round_no] + list(data.values())
    placeholders = ", ".join("?" for _ in columns)
    if data:
        conflict = ("ON CONFLICT(run_id, round_no) DO UPDATE SET "
                    + ", ".join(f"{name} = excluded.{name}" for name in data))
    else:
        conflict = "ON CONFLICT(run_id, round_no) DO NOTHING"
    conn = connect()
    try:
        conn.execute(
            f"INSERT INTO rounds ({', '.join(columns)}) VALUES ({placeholders}) {conflict}",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def list_rounds(run_id: int) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM rounds WHERE run_id = ? ORDER BY round_no", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_rounds_by_status(run_id: int) -> Dict[str, int]:
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT COALESCE(status, 'NULL') AS status, COUNT(*) AS n
               FROM rounds WHERE run_id = ? GROUP BY 1""",
            (run_id,),
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}
    finally:
        conn.close()


def insert_apk_artifact(run_id: int, round_no: Optional[int], path: str,
                        size: Optional[int], mtime: Optional[str],
                        sha256: Optional[str], source: Optional[str]) -> None:
    conn = connect()
    try:
        conn.execute(
            """INSERT INTO apk_artifacts (run_id, round_no, path, size, mtime, sha256, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, round_no, path, size, mtime, sha256, source),
        )
        conn.commit()
    finally:
        conn.close()


def list_apk_artifacts(run_id: int) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM apk_artifacts WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_emulator_log_line(run_id: int, seq: int, line: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO emulator_log_lines (run_id, seq, ts, line) VALUES (?, ?, ?, ?)",
            (run_id, seq, now_iso(), line),
        )
        conn.commit()
    finally:
        conn.close()


def list_emulator_log_lines(run_id: int, after_seq: int = -1) -> List[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM emulator_log_lines WHERE run_id = ? AND seq > ? ORDER BY seq",
            (run_id, after_seq),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()