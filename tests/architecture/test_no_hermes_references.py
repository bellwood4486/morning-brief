"""Hermes 概念がコードベースから消えていることを検証する (ADR-012)。

PR #36 / T2.2 で Hermes Agent は廃止された。Phase 1/5 や last_digest 永続化は
T2.4 で `state_store.py` として再構築される予定だが、Hermes という名称・パスは
今後コードに復活させない。
"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_TOKENS = ("hermes_bridge", "HermesBridge", ".hermes")


def test_no_hermes_tokens_in_src() -> None:
    forbidden: list[Path] = []
    for py_file in (_PROJECT_ROOT / "src").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if any(token in text for token in _FORBIDDEN_TOKENS):
            forbidden.append(py_file)
    assert not forbidden, f"Hermes references found in src/: {forbidden}"
