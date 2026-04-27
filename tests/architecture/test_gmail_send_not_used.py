"""Gmail API は受信専用。送信用エンドポイントの呼び出しを検出 (docs/quality.md 層3)。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_no_gmail_send_calls() -> None:
    forbidden_calls = ["users().messages().send", ".send(userId="]
    found: list[str] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for call in forbidden_calls:
            if call in content:
                found.append(f"{py_file}: '{call}'")
    assert not found, f"Gmail send call found: {found}"
