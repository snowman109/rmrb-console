import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AVD_CONSOLE_DATA", str(tmp_path / "data"))