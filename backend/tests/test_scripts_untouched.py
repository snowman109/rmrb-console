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