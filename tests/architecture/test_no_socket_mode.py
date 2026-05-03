"""Slack Socket Mode の使用は全ファイルで禁止 (docs/quality.md 層3)。

常駐サーバ前提の機能を使わない方針による。Modal Cron が唯一の起点。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SCAN_ROOTS = [
    _PROJECT_ROOT / "src",
]
_EXTRA_FILES = [
    _PROJECT_ROOT / "modal_app.py",
]

_FORBIDDEN_PATTERNS = [
    "SocketModeClient",
    "socket_mode_request",
    "slack_sdk.socket_mode",
]


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(root.rglob("*.py"))
    for extra in _EXTRA_FILES:
        if extra.exists():
            files.append(extra)
    return files


def test_no_socket_mode() -> None:
    forbidden: list[str] = []
    for py_file in _iter_py_files():
        text = py_file.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in text:
                forbidden.append(f"{py_file}: {pattern}")
    assert not forbidden, f"Socket Mode usage found: {forbidden}"
