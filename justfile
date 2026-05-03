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

# 型チェック: mypy と pyright を並走させる
# - mypy: strict 設定による従来の型検査
# - pyright: IDE (Pylance) と同じエンジン。CLI で走らせることで「IDE では赤線が出るのに
#            just check では気付けない」という指摘の非対称を防ぐ
type:
    uv run mypy src/
    uv run pyright src/

# ユニットテスト
test:
    uv run pytest tests/unit/

# 統合テスト (外部 API モック前提)
test-int:
    uv run pytest tests/integration/ -m "not external"

# 設計遵守 (アーキテクチャ) テスト
test-arch:
    uv run pytest tests/architecture/

# markdown lint
md-lint:
    uv run pymarkdown -c .pymarkdown.json scan --recurse --respect-gitignore .

# 一括検証 (commit 前に必ず実行)
check: lint fmt-check type test test-arch md-lint

# Modal ドライラン (送信せず最終 Markdown を stdout に出す)
dry-run:
    uv run modal run modal_app.py::digest_job --dry-run

# Modal 本番実行 (手動トリガ)
run:
    uv run modal run modal_app.py::digest_job

# Modal にデプロイ (Cron 有効化)
deploy:
    uv run modal deploy modal_app.py

# pre-commit hook をインストール (clone 後に 1 度だけ)
install-hooks:
    uv run pre-commit install
