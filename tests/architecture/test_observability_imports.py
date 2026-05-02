"""langsmith / logfire の import は src/digest/observability.py 以外で禁止 (docs/quality.md 層3)。

observability バックエンドの差し替え時の影響範囲を 1 ファイルに閉じ込める。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "observability.py").resolve()

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


def _has_import(text: str, module: str) -> bool:
    """ファイルテキストに module の import 文が含まれているか判定する。"""
    return f"import {module}" in text or f"from {module}" in text


def test_langsmith_only_in_observability() -> None:
    forbidden: list[Path] = []
    for py_file in _iter_py_files():
        if py_file.resolve() == _ALLOWED:
            continue
        if _has_import(py_file.read_text(encoding="utf-8"), "langsmith"):
            forbidden.append(py_file)
    assert not forbidden, f"langsmith found outside observability.py: {forbidden}"


def test_logfire_only_in_observability() -> None:
    forbidden: list[Path] = []
    for py_file in _iter_py_files():
        if py_file.resolve() == _ALLOWED:
            continue
        if _has_import(py_file.read_text(encoding="utf-8"), "logfire"):
            forbidden.append(py_file)
    assert not forbidden, f"logfire found outside observability.py: {forbidden}"
