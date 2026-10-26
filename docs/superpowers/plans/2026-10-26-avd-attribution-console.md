# AVD 归因测试控制台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `avd_rounds.py` 包装成本地 Web 控制台：网页配置 URL/轮数，串行跑完每一轮，全部中间数据落 SQLite。

**Architecture:** FastAPI 后端（路由 + 单 worker 线程 + subprocess 调原脚本）+ React/Vite/AntD 前端（构建产物由后端托管）。脚本每轮被单独调用一次（`ROUNDS=1`），worker 解析 stdout、导入每轮 CSV、快照 APK 元数据并写库。

**Tech Stack:** Python 3.9、FastAPI、uvicorn、sqlite3（stdlib）、pytest；React 18、TypeScript、Vite、Ant Design 5。

**Spec:** `docs/superpowers/specs/2026-10-26-avd-attribution-console-design.md`

## Global Constraints

- 所有路径相对项目根 `avd_attribution_console/`，除非另注。
- `avd_rounds.py` 与 `cdp_click.mjs` **禁止修改**；它们的 sha256 必须始终等于 `backup/` 里的备份。
- 子进程每轮环境固定为：`ROUNDS=1`、`PLAN=wipe`、`URL=<页面传入>`、`AVD=<配置>`、`SERIAL=emulator-5554`、`OUT=<run_dir>/round_<r>.csv`、`ANDROID_HOME=<sdk_root>`、`ANDROID_SDK_ROOT=<sdk_root>`、`PYTHONUNBUFFERED=1`，`PATH` 前置 `<sdk_root>/platform-tools`。
- 子进程 `cwd` = 脚本所在目录（`cdp_click.mjs` 按脚本目录解析）。
- 同一时间只允许一个 run；重复提交进入内存队列。
- 环境失败集合固定为 `{BOOT_FAIL, NO_PAGE, NO_APK, CLICK_FAIL, INSTALL_FAIL, CSV_MISSING}`；`OPEN_FAIL`、`OPEN_NO_CHANNEL` **不算**。
- 连续 3 轮环境失败即中止，剩余轮次写 `skipped`，run 置 `failed`。
- 取消/中断是终态，不做续跑。
- 服务监听 `127.0.0.1:8787`；数据库 `data/app.db`。
- 界面文案中文；轮数范围 1–1000。
- 测试数据目录通过环境变量 `AVD_CONSOLE_DATA` 隔离。

## Review Focus

1. **模拟器端口漂移**：脚本启动模拟器时不带 `-port`，若 5554 被占会落到 5556，而 `SERIAL` 仍写 `emulator-5554`。预期：worker 明确报错并中止，而不是无限等待。测试落在 Task 3。
2. **APK 元数据被下一轮覆盖**：每轮脚本都写 `/tmp/avd_rounds/round1.apk`。预期：本轮结束立刻采集 size/mtime/sha256，再进入下一轮。测试落在 Task 4。
3. **脚本崩溃导致 CSV 缺失**：预期仍保留 stdout 解析出的部分轮次记录并标记 `CSV_MISSING`，不能整轮静默消失。测试落在 Task 4。
4. **`OPEN_FAIL` 被误判成环境失败**：上次 100 轮里 88 轮是 `OPEN_FAIL`。预期：连续 `OPEN_FAIL` 不会触发中止。测试落在 Task 5。
5. **取消后模拟器残留**：模拟器在脚本进程组之外。预期：`adb emu kill` 失败时按 `-avd <AVD>` 兜底杀进程。测试落在 Task 5。

---

## Task 1: 项目骨架、配置与 SQLite schema

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/test_db.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: 无
- Produces:
  - `config.PROJECT_DIR: Path`、`config.data_dir() -> Path`、`config.config_path() -> Path`、`config.db_path() -> Path`
  - `config.load_config() -> Dict[str, Any]`、`config.save_config(updates: Dict[str, Any]) -> Dict[str, Any]`
  - `db.connect() -> sqlite3.Connection`、`db.init_db() -> None`
  - `db.create_run(url, rounds, avd, serial, pkg, plan, sdk_root, script_path, out_dir) -> int`
  - `db.update_run(run_id: int, **fields) -> None`、`db.get_run(run_id: int) -> Optional[dict]`
  - `db.list_runs(limit: int = 50, offset: int = 0) -> List[dict]`
  - `db.mark_interrupted_runs() -> int`
  - `db.insert_log_line(run_id, seq, stream, line) -> None`、`db.list_log_lines(run_id) -> List[dict]`
  - `db.insert_event(run_id, round_no, kind, message) -> None`
  - `db.upsert_round(run_id, round_no, data: dict) -> None`、`db.list_rounds(run_id) -> List[dict]`
  - `db.insert_apk_artifact(run_id, round_no, path, size, mtime, sha256, source) -> None`
  - `db.insert_emulator_log_line(run_id, seq, line) -> None`
  - `db.count_rounds_by_status(run_id) -> Dict[str, int]`

- [ ] **Step 1: 建目录、初始化 git、写依赖与忽略文件**

```bash
cd avd_attribution_console
git init
mkdir -p backend/app backend/tests data/runs
touch backend/app/__init__.py
```

`backend/requirements.txt`：

```
fastapi>=0.110,<1
uvicorn>=0.29,<1
pytest>=8
httpx>=0.27
```

`.gitignore`：

```
.venv/
__pycache__/
data/app.db*
data/runs/
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: 写失败的 config 测试**

`backend/tests/conftest.py`：

```python
import pytest

@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AVD_CONSOLE_DATA", str(tmp_path / "data"))
```

`backend/tests/test_config.py`：

```python
from pathlib import Path

from app.config import config_path, load_config, save_config


def test_load_config_creates_defaults():
    cfg = load_config()
    assert cfg["default_rounds"] == 3
    assert Path(cfg["script_path"]).name == "avd_rounds.py"
    assert config_path().exists()


def test_save_config_persists_partial_update():
    save_config({"default_rounds": 100})
    cfg = load_config()
    assert cfg["default_rounds"] == 100
    assert cfg["default_url"].startswith("https://")
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 4: 实现 `backend/app/config.py`**

```python
DEFAULTS = {
    "sdk_root": str(Path.home() / "Library/Android/sdk"),
    "script_path": str(PROJECT_DIR.parent / "avd_rounds.py"),
    "default_url": "https://download.peopledailyhealth.com/?channelCode=wdb-ltt",
    "default_avd": "Pixel_6_API_34",
    "default_rounds": 3,
}

def data_dir() -> Path      # 读 AVD_CONSOLE_DATA，默认 PROJECT_DIR/"data"，不存在则创建
def config_path() -> Path   # data_dir()/"config.json"
def load_config() -> Dict[str, Any]      # 合并 DEFAULTS 与文件内容
def save_config(updates) -> Dict[str, Any]  # 合并后原子写回，返回新配置
```

`PROJECT_DIR = Path(__file__).resolve().parents[2]`（即 `avd_attribution_console/`）。

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 6: 写失败的 db 测试**

`backend/tests/test_db.py`：

```python
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
```

- [ ] **Step 7: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_db.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 8: 实现 `backend/app/db.py`**

schema 按设计文档第 6 节：表 `runs`、`rounds`（唯一约束 `(run_id, round_no)`）、`round_events`、`log_lines`、`apk_artifacts`、`emulator_log_lines`，索引 `(run_id, round_no)`、`(run_id, seq)`。

实现要点：
- `connect()` 设置 `row_factory = sqlite3.Row`、`PRAGMA journal_mode=WAL`、`PRAGMA foreign_keys=ON`
- `init_db()` 用 `CREATE TABLE IF NOT EXISTS`，可重复调用
- `upsert_round` 用 `INSERT ... ON CONFLICT(run_id, round_no) DO UPDATE SET ...`，只更新传入的键
- `update_run` 白名单字段，禁止拼入任意列名
- `mark_interrupted_runs()` 把 `status='running'` 改成 `'interrupted'`，返回影响行数
- 每个函数独立 `connect()`，不共享连接

- [ ] **Step 9: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_db.py -v`
Expected: 3 passed

- [ ] **Step 10: 提交**

```bash
git add .gitignore backend/requirements.txt backend/app backend/tests
git commit -m "feat: scaffold backend config and sqlite schema"
```

---

## Task 2: stdout 解析与 CSV 导入

**Files:**
- Create: `backend/app/parser.py`
- Create: `backend/tests/test_parser.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `parser.ENV_FAILURE_STATUSES: Set[str]`
  - `parser.Event`（`kind: str`、`message: str`）
  - `parser.parse_line(line: str) -> Optional[Event]`
  - `parser.parse_run_meta(line: str) -> Optional[Tuple[str, str]]`
  - `parser.is_environment_failure(status: str) -> bool`
  - `parser.import_csv(path: Path) -> Optional[dict]`，键为 `action, android_id_before, android_id_after, public_ip, clicked_at, click_url, apk_url, install_at, open_at, installer, first_install, channel, app_version, status, log_excerpt, apk_src`

- [ ] **Step 1: 写失败的 parser 测试**

`backend/tests/test_parser.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_parser.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.parser'`

- [ ] **Step 3: 实现 `backend/app/parser.py`**

正则表按设计文档第 7 节；`click_fail` 由 `click_ok: False` 判定；未知行返回 `None`。`import_csv` 用 `csv.DictReader`，缺文件返回 `None`，`reset→action`、`openinstall_channel→channel`，其余同名列直取。

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_parser.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/parser.py backend/tests/test_parser.py
git commit -m "feat: parse script stdout and round csv"
```

---

## Task 3: 模拟器辅助（端口、启动、终止）

**Files:**
- Create: `backend/app/emulator.py`
- Create: `backend/tests/test_emulator.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `emulator.adb_bin(sdk_root: str) -> str`
  - `emulator.list_devices(sdk_root: str) -> List[str]`
  - `emulator.device_booted(sdk_root: str, serial: str) -> bool`
  - `emulator.emulator_port(serial: str) -> Optional[int]`
  - `emulator.ensure_emulator(sdk_root: str, avd: str, serial: str, timeout: int = 480) -> None`
  - `emulator.kill_emulator(sdk_root: str, serial: str, avd: str) -> None`

- [ ] **Step 1: 写失败的测试（端口解析 + 端口漂移报错）**

`backend/tests/test_emulator.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_emulator.py -v`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现 `backend/app/emulator.py`**

要点：
- `adb_bin`：`<sdk_root>/platform-tools/adb` 存在则用它，否则 `shutil.which("adb")`，再不行抛 `RuntimeError`
- `ensure_emulator`：若目标 serial 已 booted 直接返回；**启动前先列一次 `emulator-*`：若目标 serial 不在、却存在其他 `emulator-<port>`，直接抛 `RuntimeError("expected <serial>, found <actual>")`**；确认没有冲突后才校验 `emulator_port(serial)` 并用 `-port <port>` 启动 `emulator -avd <avd> -no-snapshot -no-audio -gpu auto -dns-server 223.5.5.5,119.29.29.29`（`start_new_session=True`，输出写 `data_dir()/emulator_boot.log`），轮询到 booted；超时前若发现 `emulator-*` 只有别的端口，抛 `RuntimeError("expected <serial>, found <actual>")`
- `kill_emulator`：`adb -s <serial> emu kill` → 2 秒后复查 → 重试一次 → 仍在则 `pkill -f -- "-avd <avd>"`

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_emulator.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/emulator.py backend/tests/test_emulator.py
git commit -m "feat: emulator helpers with port guard"
```

---

## Task 4: 单轮执行（子进程、日志、CSV、APK 快照）

**Files:**
- Create: `backend/app/worker.py`
- Create: `backend/tests/fixtures/fake_avd_rounds.py`
- Create: `backend/tests/test_worker_round.py`

**Interfaces:**
- Consumes: `config.load_config`、`db.*`、`parser.*`、`emulator.ensure_emulator`
- Produces:
  - `worker.RunWorker(config_provider: Callable[[], dict])`
  - `RunWorker.execute(run_id: int) -> None`（同步执行一个 run，测试直接调用）
  - `RunWorker._run_round(run_id: int, round_no: int, cfg: dict, run: dict) -> dict`
  - 常量 `worker.ROUND_TIMEOUT = 1800`、`worker.APK_PATH = "/tmp/avd_rounds/round1.apk"`、`worker.EMULATOR_LOG = "/tmp/avd_rounds/emulator_wipe.log"`

- [ ] **Step 1: 写假脚本 fixture**

`backend/tests/fixtures/fake_avd_rounds.py`：读环境变量 `OUT`、`FAKE_STATUS`（默认 `OK`）、`FAKE_SLEEP`（默认 0）、`FAKE_APK`（默认空），打印与真实脚本同形的行，并按 17 列写 CSV：

```python
#!/usr/bin/env python3
import csv, os, time
out = os.environ["OUT"]
status = os.environ.get("FAKE_STATUS", "OK")
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
print("model: sdk_gphone64_arm64")
print("qemu: 1")
print("plan: 1 rounds {'wipe': 1}")
print("=== round 1/1 (wipe) ===")
print("  cold boot with -wipe-data ...")
print("  android_id: before123 -> after456")
print("  click ok: True apk: https://x/a.apk")
print("  host download ok: 81587534 bytes")
print("  pm install ...")
print("    app tap: 同意")
print("  channel: wdb-ltt | status: " + status)
csv.writer(open(out, "w", newline="", encoding="utf-8")).writerow([
    "round","reset","android_id_before","android_id_after","public_ip",
    "clicked_at","click_url","apk_url","install_at","open_at","installer",
    "first_install","openinstall_channel","app_version","status",
    "log_excerpt","apk_src"])
csv.writer(open(out, "a", newline="", encoding="utf-8")).writerow([
    1,"wipe","before123","after456","1.2.3.4","t1","cu","au","t2","t3",
    "null","2026-10-26","wdb-ltt","2.7.1",status,"excerpt","click"])
```

- [ ] **Step 2: 写失败的 worker 单轮测试**

`backend/tests/test_worker_round.py`：

```python
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


def test_apk_metadata_snapshotted_before_next_round(tmp_path, monkeypatch):
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
    arts = db.list_apk_artifacts(run_id)
    assert len(arts) == 1
    assert arts[0]["size"] == 1024
    assert len(arts[0]["sha256"]) == 64
```

> 这三个测试需要 `db.list_events(run_id)`、`db.list_log_lines(run_id)`、`db.list_apk_artifacts(run_id)`；在本任务中把它们补进 `db.py`（简单 `SELECT ... ORDER BY id/seq`，`runs`/`apk_artifacts` 用 `id`，日志用 `seq`）。

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_worker_round.py -v`
Expected: FAIL，`worker` 模块或函数不存在

- [ ] **Step 4: 实现 `backend/app/worker.py` 的单轮能力**

要点：
- `_build_env(cfg, run, round_no, out_csv)` 按 Global Constraints 组装
- `Popen([sys.executable, cfg["script_path"]], cwd=str(Path(cfg["script_path"]).parent), env=..., stdout=PIPE, stderr=STDOUT, text=True, bufsize=1, start_new_session=True)`
- 读流：单独线程逐行 `queue.put`，主线程 `get(timeout=1)`，同时检查取消标志与 `ROUND_TIMEOUT`；超时对进程组 `SIGTERM`，3 秒后 `SIGKILL`
- 每行写 `log_lines`（seq 从 1 递增），解析事件写 `round_events`，`model/qemu` 写回 `runs`
- 轮末：`import_csv` 成功 → `source="csv"`；失败 → 从事件拼 `android_id_before/after`、`channel/status`，状态 `CSV_MISSING`、`source="stdout"`
- APK 快照：文件存在才记录，sha256 用流式读取
- 状态映射：CSV 的 `status` 原样入库

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_worker_round.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/worker.py backend/app/db.py backend/tests
git commit -m "feat: single-round worker with csv import and apk snapshot"
```

---

## Task 5: 运行循环、连续失败中止、取消

**Files:**
- Modify: `backend/app/worker.py`
- Modify: `backend/app/db.py`
- Create: `backend/tests/test_worker_run.py`

**Interfaces:**
- Consumes: Task 4 的 `RunWorker.execute` / `_run_round`
- Produces:
  - `RunWorker.submit(url: str, rounds: int, avd: str) -> int`
  - `RunWorker.cancel(run_id: int) -> bool`
  - `RunWorker.is_busy() -> bool`
  - `RunWorker.start() -> None`（守护线程消费队列）
  - `worker.MAX_CONSECUTIVE_ENV_FAILURES = 3`

- [ ] **Step 1: 写失败的中止/取消测试**

`backend/tests/test_worker_run.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_worker_run.py -v`
Expected: FAIL，`execute` 未实现多轮/中止/取消

- [ ] **Step 3: 实现运行循环**

要点：
- `execute(run_id)`：置 running → 记录 `EMULATOR_LOG` 起始 offset → 循环 `r in 1..rounds` → 每轮前检查取消 → `ensure_emulator` → `_run_round` → 连续失败计数（`is_environment_failure`）累计到 3 即中止 → 轮间短暂 sleep
- 中止：剩余轮次逐条 `upsert_round(..., {"status": "skipped", "source": "worker"})`；run `failed`，`error` 写如 `BOOT_FAIL x3`
- `cancel(run_id)`：置事件；对当前进程组 `SIGTERM`；返回是否命中正在跑的 run
- 结束时：`kill_emulator` 仅在取消/中止时调用；导入模拟器日志新增行（按字节 offset 读取）
- `submit`：建 run 行、入队、返回 id；`start` 启守护线程

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_worker_run.py -v`
Expected: 3 passed

- [ ] **Step 5: 跑全部后端测试**

Run: `cd backend && python3 -m pytest -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/worker.py backend/app/db.py backend/tests/test_worker_run.py
git commit -m "feat: run loop with abort threshold and cancel"
```

---

## Task 6: FastAPI 应用与 API

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `config`、`db`、`worker.RunWorker`、`emulator`
- Produces:
  - `app.main.app`（FastAPI 实例）
  - 路由：`GET/PUT /api/config`、`GET /api/avds`、`POST /api/runs`、`GET /api/runs`、`GET /api/runs/{id}`、`GET /api/runs/{id}/rounds`、`GET /api/runs/{id}/events`、`GET /api/runs/{id}/logs`、`POST /api/runs/{id}/cancel`、`GET /api/runs/{id}/export.csv`

- [ ] **Step 1: 写失败的 API 测试**

`backend/tests/test_api.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd backend && python3 -m pytest tests/test_api.py -v`
Expected: FAIL，`app.main` 不存在

- [ ] **Step 3: 实现 `backend/app/main.py`**

要点：
- 启动事件：`init_db()`、`db.mark_interrupted_runs()`、`worker.start()`
- `POST /api/runs`：`rounds` 用 `Field(ge=1, le=1000)`；`avd` 缺省取配置 `default_avd`；返回 `{"id": run_id}`
- `GET /api/runs/{id}` 返回 `{"run": ..., "counts": count_rounds_by_status(id)}`
- `GET /api/avds`：扫描 `Path.home()/".android/avd"/*.ini` 取文件名（去 `.ini`）
- `GET /api/runs/{id}/export.csv`：复用 CSV 列头，`StreamingResponse`，UTF-8
- 静态托管：`frontend/dist` 存在时，`/assets` 挂载 + 其他 GET 回 `index.html`；不存在时 `/` 返回提示
- 代码里通过模块级 `worker = RunWorker(config.load_config)` 暴露，测试可 monkeypatch

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd backend && python3 -m pytest tests/test_api.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: fastapi routes for runs, events, logs, export"
```

---

## Task 7: 前端骨架（Vite + TS + AntD + 类型与 API 客户端）

**Files:**
- Create: `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`
- Create: `frontend/src/main.tsx`、`frontend/src/App.tsx`
- Create: `frontend/src/types.ts`、`frontend/src/api.ts`
- Create: `frontend/src/theme.ts`

**Interfaces:**
- Consumes: 后端 API（Task 6）
- Produces:
  - `types.ts`：`Config`、`Run`、`RoundRow`、`RunEvent`、`LogLine`、`RunDetail`
  - `api.ts`：`getConfig()`、`putConfig(patch)`、`listAvds()`、`createRun({url, rounds, avd?})`、`listRuns()`、`getRun(id)`、`getRounds(id)`、`getEvents(id, afterId)`、`getLogs(id, afterSeq)`、`cancelRun(id)`、`exportCsvUrl(id)`

- [ ] **Step 1: 初始化前端**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install react@18 react-dom@18 @types/react@18 @types/react-dom@18
npm install antd
```

`vite.config.ts` 增加开发代理：

```ts
server: { proxy: { '/api': 'http://127.0.0.1:8787' } },
build: { outDir: 'dist' }
```

- [ ] **Step 2: 写类型与 API 客户端**

`types.ts` 字段与后端 JSON 一一对应（snake_case 直用）。`api.ts` 统一 `fetch` 封装，非 2xx 抛 `Error(body.detail ?? statusText)`。

- [ ] **Step 3: 写布局骨架**

`App.tsx` 用 AntD `Layout`：`Sider`（历史列表占位）+ `Content`；`ConfigProvider` 使用中文 `zhCN` locale 与 `theme.ts` 的色板。暂时渲染标题和占位卡片。

- [ ] **Step 4: 验证构建**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 无类型错误，`dist/` 生成

- [ ] **Step 5: 提交**

```bash
git add frontend
git commit -m "feat: frontend scaffold with antd and api client"
```

---

## Task 8: 新建运行表单、运行概览与轮询

**Files:**
- Create: `frontend/src/components/NewRunForm.tsx`
- Create: `frontend/src/components/RunOverview.tsx`
- Create: `frontend/src/hooks/useRunPolling.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api.ts`、`types.ts`
- Produces:
  - `NewRunForm({config, busy, onSubmit})`，`onSubmit(v: {url: string; rounds: number; avd: string})`
  - `RunOverview({run, counts, onCancel})`
  - `useRunPolling(runId: number | null) -> {run, counts, rounds, refresh}`，2 秒轮询

- [ ] **Step 1: 实现表单**

AntD `Form`：URL `Input`、rounds `InputNumber`（1–1000）、AVD `Select`（来自 `listAvds`）。默认值取 `/api/config`。提交后清空错误、显示排队提示。

- [ ] **Step 2: 实现概览**

`Statistic`：总轮数、OK、OPEN_NO_CHANNEL、OPEN_FAIL、失败、已用时长；`Progress` 显示 `已完成/总数`；状态 `Tag`；取消按钮旁固定提示「取消后不能续跑」。

- [ ] **Step 3: 实现轮询 hook**

`setInterval` 2 秒调 `getRun` + `getRounds`；组件卸载清理；`run.status` 进入终态后停止轮询。

- [ ] **Step 4: 验证构建**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 通过

- [ ] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "feat: new run form and live overview"
```

---

## Task 9: 轮次表、事件时间线、日志与历史侧栏

**Files:**
- Create: `frontend/src/components/RoundsTable.tsx`
- Create: `frontend/src/components/EventTimeline.tsx`
- Create: `frontend/src/components/LogViewer.tsx`
- Create: `frontend/src/components/HistorySidebar.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api.ts`、`types.ts`
- Produces:
  - `RoundsTable({rounds})`
  - `EventTimeline({events})`
  - `LogViewer({runId, active})` — 内部按 `after_seq` 增量拉取，最多保留 2000 行
  - `HistorySidebar({selectedId, onSelect})`

- [ ] **Step 1: 轮次表**

AntD `Table`，`rowKey="round_no"`；列：轮次、action、android_id 前→后、status（`Tag` 上色）、channel、apk_src、clicked_at、open_at；支持按 status 过滤与排序；`expandable` 展开显示 `log_excerpt`。

- [ ] **Step 2: 事件时间线**

`Timeline` 渲染最近 200 条事件，kind 映射中文标签（如 `click_ok → 点击下载成功`）。

- [ ] **Step 3: 日志面板**

`Collapse` 内深色 `pre`；展开时开始增量拉取，折叠时暂停；滚动到底部跟随最新。

- [ ] **Step 4: 历史侧栏**

`listRuns()` 渲染 `List`，显示状态 Tag、URL、轮数、创建时间；点击切换 `selectedId`。

- [ ] **Step 5: 验证构建**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 通过

- [ ] **Step 6: 提交**

```bash
git add frontend/src
git commit -m "feat: rounds table, timeline, log viewer, history"
```

---

## Task 10: 静态托管、README 与端到端验收

**Files:**
- Modify: `backend/app/main.py`（确认静态托管逻辑）
- Create: `README.md`
- Create: `backend/tests/test_scripts_untouched.py`

**Interfaces:**
- Consumes: Task 1–9 全部
- Produces: 可本地启动的完整应用

- [ ] **Step 1: 加脚本只读校验测试**

`backend/tests/test_scripts_untouched.py`：

```python
import hashlib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
NEW_CHAT = PROJECT.parent
EXPECTED = {
    "avd_rounds.py": "23959740bd1869022d5d5665c138ef7e1392bb8e03d66f0d2ef2432742227a56",
    "cdp_click.mjs": "6f40b0f90e5c38c9857e418d9bdb0679710b0572992a044d51ab1f789c7fb6f2",
}


def test_original_scripts_untouched():
    for name, digest in EXPECTED.items():
        actual = hashlib.sha256((NEW_CHAT / name).read_bytes()).hexdigest()
        assert actual == digest, f"{name} 被修改了"
```

- [ ] **Step 2: 运行全部后端测试**

Run: `cd backend && python3 -m pytest -v`
Expected: 全部 passed（含只读校验）

- [ ] **Step 3: 前端构建并启动**

```bash
cd frontend && npm run build
cd .. && python3 -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8787
```

Run: `curl -s http://127.0.0.1:8787/api/config`
Expected: 返回默认配置 JSON

- [ ] **Step 4: 浏览器冒烟**

打开 `http://127.0.0.1:8787`：能看到表单、历史侧栏；提交 `rounds=1` 后概览出现 running，轮次表最终出现 1 行，状态为脚本实际结果；日志面板能看到逐行输出。

- [ ] **Step 5: 写 README**

内容：依赖安装、前端构建、启动命令、`ANDROID_HOME` 坑（当前 shell 指向失效的 Caskroom 路径，应用用配置值覆盖）、AVD 准备、脚本只读说明、取消不可续跑、平台核对仍需人工。

- [ ] **Step 6: 提交**

```bash
git add README.md backend/tests/test_scripts_untouched.py backend/app/main.py
git commit -m "chore: static hosting, readme, and script integrity test"
```

---

## Self-Review 记录

- 规格覆盖：数据模型（Task 1/4/5）、解析（Task 2）、模拟器与端口（Task 3）、单轮与 APK 快照（Task 4）、中止/取消（Task 5）、API（Task 6）、前端（Task 7–9）、部署与验收（Task 10）。
- 类型一致性：`RoundRow.round_no`、`Event.kind/message`、`Run.status` 在 API 与前端 types 中同名。
- 五个 Review Focus 均有对应测试：Task 3（端口漂移）、Task 4（APK 快照、CSV 缺失）、Task 5（OPEN_FAIL 不中止、取消清理）。
- 计划未包含的：真实 100 轮长跑（属于验收后的使用行为，不在实现任务内）。