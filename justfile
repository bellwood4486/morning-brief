default:
    @just --list

# 依存セットアップ
sync:
    uv sync

# ruff lint
lint:
    uv run ruff check .

# ruff format (適用)
fmt:
    uv run ruff format .

# ruff format (チェックのみ)
fmt-check:
    uv run ruff format --check .

# mypy 型チェック
type:
    uv run mypy src/

# ユニットテスト
test:
    uv run pytest tests/unit/

# 統合テスト (外部 API モック前提)
test-int:
    uv run pytest tests/integration/ -m "not external"

# 設計遵守 (アーキテクチャ) テスト
test-arch:
    uv run pytest tests/architecture/

# 一括検証 (commit 前に必ず実行)
check: lint fmt-check type test test-arch

# Modal ドライラン (送信せず最終 Markdown を stdout に出す)
dry-run:
    modal run modal_app.py::digest_job --dry-run

# Modal 本番実行 (手動トリガ)
run:
    modal run modal_app.py::digest_job
