"""コミット対象ファイルに API キー風文字列が混入していないことを保証する (docs/quality.md 層3)。

pre-commit hook (gitleaks) と検出意図は重複するが、
`just check` からも独立に検査する経路として保持する。
"""

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SCAN_ROOTS = [
    _PROJECT_ROOT / "src",
    _PROJECT_ROOT / "seeds",
    _PROJECT_ROOT / "scripts",
]
_EXTRA_FILES = [
    _PROJECT_ROOT / "modal_app.py",
    _PROJECT_ROOT / "config.yaml",
    _PROJECT_ROOT / "config.example.yaml",
    _PROJECT_ROOT / ".env.example",
]

# プレフィックス + 長さ要件で誤検知を防ぐ
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Slack bot token", re.compile(r"xoxb-[A-Za-z0-9-]{20,}")),
    ("Slack user token", re.compile(r"xoxp-[A-Za-z0-9-]{20,}")),
    ("OpenAI key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("GitHub PAT", re.compile(r"ghp_[A-Za-z0-9]{36}")),
]

# テスト fixture 用の偽トークンに対する保険 (tests/ は走査外だが念のため)
_FALSE_POSITIVES = re.compile(r"xox[bp]-fake")


def _iter_target_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file())
    for extra in _EXTRA_FILES:
        if extra.exists():
            files.append(extra)
    return files


def test_no_secrets_in_committed_files() -> None:
    offenders: list[str] = []
    for path in _iter_target_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in _SECRET_PATTERNS:
            for m in pattern.finditer(content):
                if _FALSE_POSITIVES.search(m.group(0)):
                    continue
                offenders.append(f"{path.relative_to(_PROJECT_ROOT)}: {label}")
    assert not offenders, "Secret-like strings detected:\n" + "\n".join(offenders)
