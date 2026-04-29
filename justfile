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

# 秘匿情報検出 (mise install で gitleaks が入る前提、未インストール時は grep フォールバック)
secrets:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v gitleaks >/dev/null 2>&1; then
        gitleaks detect --source . --no-banner --redact --config .gitleaks.toml
    else
        echo "gitleaks not found, falling back to grep" >&2
        if git grep -nE \
            'xoxb-[A-Za-z0-9-]{20,}|xoxp-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{32,}|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}' \
            -- ':!tests/' ':!.gitleaks.toml' \
            | grep -vE 'xox[bp]-fake'; then
            echo "secret-like strings detected by grep fallback" >&2
            exit 1
        fi
        echo "grep fallback: no secrets detected"
    fi

# 一括検証 (commit 前に必ず実行)
check: secrets lint fmt-check type test test-arch md-lint

# Modal ドライラン (送信せず最終 Markdown を stdout に出す)
dry-run:
    modal run modal_app.py::digest_job --dry-run

# Modal 本番実行 (手動トリガ)
run:
    modal run modal_app.py::digest_job
