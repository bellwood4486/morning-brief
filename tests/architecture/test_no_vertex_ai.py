"""Vertex AI の import は全ファイルで禁止 (docs/quality.md 層3)。

Gemini API は google-genai SDK に統一。google-cloud-aiplatform / vertexai パッケージの使用は不可。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    return f"import {module}" in text or f"from {module}" in text


def test_no_vertex_ai_imports() -> None:
    forbidden: list[str] = []
    for py_file in _iter_py_files():
        text = py_file.read_text(encoding="utf-8")
        for module in ("google.cloud.aiplatform", "vertexai"):
            if _has_import(text, module):
                forbidden.append(f"{py_file}: {module}")
    assert not forbidden, f"Vertex AI imports found: {forbidden}"
