import json
import os
from pathlib import Path
from typing import Any, Dict

PROJECT_DIR = Path(__file__).resolve().parents[2]

DEFAULTS: Dict[str, Any] = {
    "sdk_root": str(Path.home() / "Library/Android/sdk"),
    "script_path": str(PROJECT_DIR.parent / "avd_rounds.py"),
    "default_url": "https://download.peopledailyhealth.com/?channelCode=wdb-ltt",
    "default_avd": "Pixel_6_API_34",
    "default_rounds": 3,
}


def data_dir() -> Path:
    d = Path(os.environ.get("AVD_CONSOLE_DATA", str(PROJECT_DIR / "data")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return data_dir() / "config.json"


def db_path() -> Path:
    return data_dir() / "app.db"


def _read_saved() -> Dict[str, Any]:
    p = config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg.update(_read_saved())
    if not config_path().exists():
        save_config({})
    return cfg


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg.update(_read_saved())
    cfg.update(updates)
    p = config_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return cfg