import hashlib
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app import db, emulator, parser

ROUND_TIMEOUT = 1800
APK_PATH = "/tmp/avd_rounds/round1.apk"
EMULATOR_LOG = "/tmp/avd_rounds/emulator_wipe.log"


def _pump(stream, q: "queue.Queue[Optional[str]]") -> None:
    try:
        for line in stream:
            q.put(line)
    finally:
        q.put(None)


class RunWorker:
    def __init__(self, config_provider: Callable[[], dict]):
        self.config_provider = config_provider
        self.cancel_event = threading.Event()
        self.last_exit_code: Optional[int] = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def execute(self, run_id: int) -> None:
        run = db.get_run(run_id)
        if run is None:
            return
        cfg = self.config_provider() or {}
        db.update_run(run_id, status="running", started_at=db.now_iso())
        status = "succeeded"
        try:
            sdk_root = run["sdk_root"] or cfg.get("sdk_root", "")
            emulator.ensure_emulator(sdk_root, run["avd"], run["serial"])
            for round_no in range(1, int(run["rounds"]) + 1):
                if self.cancel_event.is_set():
                    status = "canceled"
                    break
                self._run_round(run_id, round_no, cfg, run)
        except Exception as exc:  # noqa: BLE001 - failure is recorded, not raised
            status = "failed"
            db.update_run(run_id, error=str(exc))
        finally:
            db.update_run(run_id, status=status, finished_at=db.now_iso(),
                          exit_code=self.last_exit_code)

    def _run_round(self, run_id: int, round_no: int, cfg: dict, run: dict) -> dict:
        out_csv = Path(run["out_dir"]) / f"round_{round_no}.csv"
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        env = self._build_env(cfg, run, round_no, out_csv)

        seq = len(db.list_log_lines(run_id))
        events: List[parser.Event] = []
        proc = subprocess.Popen(
            [sys.executable, cfg["script_path"]],
            cwd=str(Path(cfg["script_path"]).parent),
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=True,
        )
        q: "queue.Queue[Optional[str]]" = queue.Queue()
        threading.Thread(target=_pump, args=(proc.stdout, q), daemon=True).start()

        started = time.time()
        timed_out = False
        while True:
            if self.cancel_event.is_set():
                self._terminate(proc)
                break
            if time.time() - started > ROUND_TIMEOUT:
                timed_out = True
                self._terminate(proc)
                break
            try:
                line = q.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            seq += 1
            line = line.rstrip("\n")
            db.insert_log_line(run_id, seq, "stdout", line)

            event = parser.parse_line(line)
            if event is not None:
                events.append(event)
                db.insert_event(run_id, round_no, event.kind, event.message)

            meta = parser.parse_run_meta(line)
            if meta is not None:
                db.update_run(run_id, **{meta[0]: meta[1]})

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        self.last_exit_code = proc.returncode

        if timed_out:
            db.insert_event(run_id, round_no, "timeout",
                            f"round exceeded {ROUND_TIMEOUT}s")
        if self.cancel_event.is_set():
            db.insert_event(run_id, round_no, "canceled", "run canceled")

        row = parser.import_csv(out_csv)
        if row is not None:
            row["source"] = "csv"
        else:
            row = self._partial_row(events)

        db.upsert_round(run_id, round_no, row)
        self._snapshot_apk(run_id, round_no)
        return row

    def _partial_row(self, events: List[parser.Event]) -> Dict[str, Any]:
        row: Dict[str, Any] = {name: None for name in parser.CSV_COLUMNS}
        row["action"] = "wipe"
        row["status"] = "CSV_MISSING"
        row["source"] = "stdout"
        for event in events:
            if event.kind == "android_id":
                before, _, after = event.message.partition(" -> ")
                row["android_id_before"] = before or None
                row["android_id_after"] = after or None
            elif event.kind in ("click_ok", "click_fail"):
                if "apk: " in event.message:
                    row["apk_url"] = event.message.split("apk: ", 1)[1] or None
            elif event.kind == "channel_status":
                channel, _, _status = event.message.rpartition(" | ")
                row["channel"] = channel or None
        return row

    def _snapshot_apk(self, run_id: int, round_no: int) -> None:
        path = Path(APK_PATH)
        if not path.exists():
            return
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds")
        db.insert_apk_artifact(run_id, round_no, str(path), stat.st_size, mtime,
                               digest.hexdigest(), "host")

    def _build_env(self, cfg: dict, run: dict, round_no: int,
                   out_csv: Path) -> Dict[str, str]:
        env = dict(os.environ)
        sdk_root = run["sdk_root"] or cfg.get("sdk_root", "")
        env.update({
            "URL": run["url"],
            "PKG": run["pkg"],
            "AVD": run["avd"],
            "SERIAL": run["serial"],
            "ROUNDS": "1",
            "PLAN": "wipe",
            "OUT": str(out_csv),
            "ANDROID_HOME": sdk_root,
            "PATH": f"{sdk_root}/platform-tools:" + env.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
        })
        return env

    def _terminate(self, proc: subprocess.Popen) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass