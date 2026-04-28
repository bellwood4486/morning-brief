from __future__ import annotations

from pathlib import Path

# Modal Image 内の seeds/ マウントは T1.10 で対応する。
# ローカル実行時はリポジトリルート直下の seeds/ を指す。
_SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"


def load_seed(name: str) -> str:
    """seeds/ 配下のファイルを文字列として読む。"""
    return (_SEEDS_DIR / name).read_text(encoding="utf-8")
