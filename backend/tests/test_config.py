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