"""googleapiclient の import は src/digest/gmail_client.py 以外で禁止 (docs/quality.md 層3)。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "gmail_client.py").resolve()


def test_googleapiclient_only_in_gmail_client() -> None:
    forbidden: list[Path] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        if py_file.resolve() == _ALLOWED:
            continue
        if "googleapiclient" in py_file.read_text(encoding="utf-8"):
            forbidden.append(py_file)
    assert not forbidden, f"googleapiclient found outside gmail_client.py: {forbidden}"
