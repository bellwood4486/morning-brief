"""slack_sdk の import は src/digest/notifiers/slack.py 以外で禁止 (docs/quality.md 層3)。

modal_app.py も検査対象に含める。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "notifiers" / "slack.py").resolve()

# 検査対象: src/ 配下の全 .py + リポジトリルートの modal_app.py
_SCAN_ROOTS = [
    _PROJECT_ROOT / "src",
]
_EXTRA_FILES = [
    _PROJECT_ROOT / "modal_app.py",
]


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(root.rglob("*.py"))
    for extra in _EXTRA_FILES:
        if extra.exists():
            files.append(extra)
    return files


def test_slack_sdk_only_in_notifier() -> None:
    forbidden: list[Path] = []
    for py_file in _iter_py_files():
        if py_file.resolve() == _ALLOWED:
            continue
        if "slack_sdk" in py_file.read_text(encoding="utf-8"):
            forbidden.append(py_file)
    assert not forbidden, f"slack_sdk found outside slack.py: {forbidden}"
