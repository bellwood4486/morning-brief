"""env への直接アクセスは src/digest/observability.py 以外で禁止 (docs/quality.md 層3)。

他モジュールは DI 経由で値を受け取る。modal_app.py は DI のエントリポイントなので対象外。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = (_PROJECT_ROOT / "src" / "digest" / "observability.py").resolve()

# src/digest/ 配下のみ検査。modal_app.py は DI のエントリポイントとして例外扱い。
_SCAN_ROOTS = [
    _PROJECT_ROOT / "src" / "digest",
]

_FORBIDDEN_PATTERNS = [
    "os.environ",
    "os.getenv",
    "dotenv",
]


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(root.rglob("*.py"))
    return files


def test_env_access_localized() -> None:
    forbidden: list[str] = []
    for py_file in _iter_py_files():
        if py_file.resolve() == _ALLOWED:
            continue
        text = py_file.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in text:
                forbidden.append(f"{py_file}: {pattern}")
    assert not forbidden, f"env access outside observability.py: {forbidden}"
