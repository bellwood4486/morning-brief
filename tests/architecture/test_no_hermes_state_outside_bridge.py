"""hermes_bridge.py 以外での `.hermes` / `last_digest.json` 直接アクセス禁止 (CLAUDE.md 制約3)。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "hermes_bridge.py").resolve()
_MARKERS = (".hermes", "last_digest.json")


def test_hermes_state_only_in_bridge() -> None:
    forbidden: list[Path] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        if py_file.resolve() == _ALLOWED:
            continue
        text = py_file.read_text(encoding="utf-8")
        if any(marker in text for marker in _MARKERS):
            forbidden.append(py_file)
    assert not forbidden, f"hermes state path found outside hermes_bridge.py: {forbidden}"
