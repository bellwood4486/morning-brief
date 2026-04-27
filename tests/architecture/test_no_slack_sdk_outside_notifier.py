"""slack_sdk の import は src/digest/notifiers/slack.py 以外で禁止 (docs/quality.md 層3)。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "notifiers" / "slack.py").resolve()


def test_slack_sdk_only_in_notifier() -> None:
    forbidden: list[Path] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        if py_file.resolve() == _ALLOWED:
            continue
        if "slack_sdk" in py_file.read_text(encoding="utf-8"):
            forbidden.append(py_file)
    assert not forbidden, f"slack_sdk found outside slack.py: {forbidden}"
