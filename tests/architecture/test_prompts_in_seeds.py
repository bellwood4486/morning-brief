"""プロンプト等の長文文字列リテラルをコードに直書きしないことを保証する (docs/quality.md 層3)。"""

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_THRESHOLD = 200


def _collect_docstring_ids(tree: ast.AST) -> set[int]:
    """モジュール/関数/クラスの docstring ノードを ID で集める。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def test_no_long_string_literals_in_src() -> None:
    offenders: list[str] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        docstring_ids = _collect_docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_ids
                and len(node.value) >= _THRESHOLD
            ):
                offenders.append(f"{py_file}:{node.lineno} (len={len(node.value)})")
    detail = ", ".join(offenders)
    assert not offenders, f"長文文字列リテラル検出。seeds/ に分離してください: {detail}"
