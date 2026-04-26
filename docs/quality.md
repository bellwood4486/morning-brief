# Quality / 検証ハーネス

このドキュメントは、Claude Code が生成した実装の妥当性を検証するためのハーネスを定義する。「動いた」「実装した」では完了とせず、ハーネスを通過することで完了とする。

ハーネスは目的別に層を分ける。「テストが通る」と「ambient agent として機能している」は別問題なので、層ごとに別の手段で検証する。

## 層1: コード品質ハーネス (機械検証)

Claude Code が `uv run` 系コマンドだけで自己完結検証できるもの。

### 1.1 構成

| ツール | 目的 | コマンド |
|--------|------|---------|
| ruff (format) | フォーマット | `uv run ruff format --check .` |
| ruff (check) | Lint | `uv run ruff check .` |
| mypy | 型 | `uv run mypy src/` |
| pytest (unit) | ユニットテスト | `uv run pytest tests/unit/` |
| pytest (integration) | 外部 API モックでの統合テスト | `uv run pytest tests/integration/ -m "not external"` |
| gitleaks 相当 | 秘匿情報検出 | `scripts/check.sh` 内に簡易実装、可能なら `gitleaks` バイナリ |

### 1.2 mypy 厳格度

Python 学習中のため、最初から厳格に。`pyproject.toml` 推奨設定:

```toml
[tool.mypy]
strict = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_return_any = true
```

### 1.3 一括実行スクリプト

`scripts/check.sh` で全部まとめて走らせる。Claude Code は **コミット前に必ず実行** することを `CLAUDE.md` でルール化済み。

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "▶ ruff format check"
uv run ruff format --check .

echo "▶ ruff lint"
uv run ruff check .

echo "▶ mypy"
uv run mypy src/

echo "▶ pytest"
uv run pytest tests/unit/ tests/integration/ tests/architecture/ -m "not external"

echo "▶ secrets check"
# gitleaks があればそれを使う、なければ簡易検出
if command -v gitleaks &> /dev/null; then
  gitleaks detect --no-banner
else
  # 簡易検出: API key 風の文字列
  ! grep -rEn '(AIza[0-9A-Za-z_-]{35}|xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+|sk-[A-Za-z0-9]{32,})' \
    --include='*.py' --include='*.md' --include='*.yaml' --include='*.yml' \
    --exclude-dir='.git' --exclude-dir='.venv' --exclude='.env*' .
fi

echo "✓ all checks passed"
```

## 層2: 仕様適合ハーネス (Acceptance Criteria)

各タスクが「完了」したと判定するための受入条件。`docs/tasks.md` の各タスクに **Given-When-Then 形式** で定義する。

### 2.1 形式

```
Given: <前提条件>
When:  <操作>
Then:  <期待される結果>
And:   <追加の期待>
```

### 2.2 強制方法

- 受入条件を満たすテストを `tests/unit/` または `tests/integration/` に書く。
- テストが通るまでタスクを「完了」と呼ばない (`CLAUDE.md` でルール化済み)。
- Claude Code が「実装した」と報告する場合、対応するテスト名を併記すること。

### 2.3 対応関係の例

| タスク | 受入条件のテスト | ファイル |
|--------|-----------------|---------|
| T1.5 fetch_unread | `test_fetch_unread_returns_emails_within_24h` | `tests/integration/test_gmail_client.py` |
| T1.7 summarize | `test_summarize_returns_digest_with_3_to_5_tldrs` | `tests/integration/test_summarize.py` |
| T1.8 formatter | `test_to_block_kit_includes_mute_button_with_sender` | `tests/unit/test_formatter.py` |

## 層3: 設計遵守ハーネス (アーキテクチャテスト)

Claude Code が急ぐと境界を破るのを機械検出する。`tests/architecture/` に置く。

### 3.1 必須テスト

#### test_no_slack_sdk_outside_notifier.py
```python
"""slack_sdk の import は src/digest/notifiers/slack.py 以外で禁止。"""
def test_slack_sdk_only_in_notifier():
    forbidden_files = []
    for py_file in Path("src").rglob("*.py"):
        if py_file == Path("src/digest/notifiers/slack.py"):
            continue
        content = py_file.read_text()
        if "slack_sdk" in content or "from slack_sdk" in content:
            forbidden_files.append(py_file)
    assert not forbidden_files, f"slack_sdk found in: {forbidden_files}"
```

#### test_no_secrets_in_code.py
レポジトリにコミットされる予定のファイルに API キー風の文字列がないかを検出。`scripts/check.sh` の secrets check と一部重複するが、pytest からも呼べるようにしておく。

#### test_prompts_in_seeds.py
```python
"""src/digest/summarize.py 等にプロンプト相当の長文文字列リテラルが無いことを検証。

heuristic: 連続する 200 文字以上の文字列リテラルを検出。
"""
def test_no_long_string_literals_in_summarize():
    content = Path("src/digest/summarize.py").read_text()
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert len(node.value) < 200, (
                f"Long string literal in summarize.py "
                f"(suggests inline prompt). Move to seeds/. "
                f"Length: {len(node.value)}"
            )
```

#### test_vertex_ai_not_used.py
```python
"""ADR-003: Vertex AI を使わない。"""
def test_no_vertex_ai_imports():
    forbidden_imports = ["google.cloud.aiplatform", "vertexai"]
    for py_file in Path("src").rglob("*.py"):
        content = py_file.read_text()
        for imp in forbidden_imports:
            assert imp not in content, f"Vertex AI import found in {py_file}"
```

#### test_gmail_send_not_used.py
```python
"""Gmail API は受信専用。送信用エンドポイントの呼び出しを検出。"""
def test_no_gmail_send_calls():
    forbidden_calls = ["users().messages().send", ".send(userId="]
    for py_file in Path("src").rglob("*.py"):
        content = py_file.read_text()
        for call in forbidden_calls:
            assert call not in content, f"Gmail send call found in {py_file}"
```

#### test_notifier_protocol_minimal.py
`Notifier` Protocol のメソッド数が膨らんでいないか検証 (最初は 2 メソッドのみ; 増やす場合は ADR を書くこと)。

### 3.2 拡張ポリシー
- 新たに「やってはいけないこと」が出てきたら、ここにテストを追加する。
- これらのテストは過剰に見えるかもしれないが、Claude Code が境界を破るのは典型的な失敗モード。投資する価値がある。

## 層4: 学習目標ハーネス (観察可能性)

ambient agent 学習目的の達成を検証する。**Sprint 2 で本格運用**。詳細は `docs/observation.md` (Sprint 2 開始時に作成) を参照。

### 4.1 観察項目
- USER.md のスナップショット (週次)
- 自動生成スキル数の推移
- 各スキルの呼び出し回数
- ダイジェストごとのフィードバック数 (👍/👎/🔥/ミュート/スレッド返信)
- LLM コスト推移

### 4.2 レポート機構
`scripts/weekly_report.py` を Modal cron で日曜に実行し、上記サマリを `#newsletter-digest` に投稿。

### 4.3 学習が起きている判定の目安
Sprint 2 の終わり頃に以下が言えれば、学習は起きていると判定:
- USER.md の初期と現在で diff が出ている。
- 自動生成スキルが 1 個以上ある。
- 「最近の傾向に合わせた要約」と言える挙動の変化が観察ログにある (主観評価でよい)。

## 層5: 実運用ハーネス (canary)

朝 06:30 に「届かない」を最も避けたい。

### 5.1 ドライラン
```bash
modal run modal_app.py::digest_job --dry-run
```
実際の Slack 投稿・Gmail ラベル更新を行わず、最終 Markdown を stdout に出す。**新しい変更を本番投入する前に必ず実行**。

### 5.2 失敗時通知
- Modal Function 内で例外を catch、`#alerts` channel に投稿。
- ただし `#alerts` も Slack なので、Slack 自体が落ちると気付けない。これは許容。

### 5.3 silent failure 防止
- Phase 2 が空 (対象メールなし) でも、`#newsletter-digest` に「本日は対象メールなし」を投稿する。
- 投稿が無いことは即「異常」と認識できる状態にする。

### 5.4 状態リカバリ
- メール処理状態は Gmail ラベル (`Newsletter/Tech/Processed`) で管理 (ADR-007)。
- 同じメールを 2 回処理しないために、Phase 5 でラベル付与に失敗したらアラート。
- リカバリ手順: Gmail UI で `Newsletter/Tech/Processed` ラベルを手動で付け外しすれば再処理可能。

## 検証チェーンの実行順序

開発時の典型的な流れ:

```
コード変更
  ↓
./scripts/check.sh  ← 層1 + 層3 + secrets
  ↓ green
新タスクの受入条件のテスト追加 ← 層2
  ↓ pytest green
modal run modal_app.py::digest_job --dry-run ← 層5 (canary)
  ↓ stdout で Markdown を目視確認
コミット → push
```

Sprint 2 以降は週次で:

```
scripts/weekly_report.py が自動実行 ← 層4
  ↓
docs/observation.md にメモを追記
```

## まとめ

| 層 | 何を保証するか | 主な実行タイミング | 責任 |
|----|----------------|-------------------|------|
| 1 | コードの基本品質 | コミット前 | Claude Code 自動 |
| 2 | 各タスクが仕様を満たす | タスク完了時 | Claude Code が受入条件のテストを書く |
| 3 | 設計境界が破られていない | コミット前 (層1 と同時) | Claude Code 自動 |
| 4 | ambient agent 学習が進んでいる | 週次、Sprint 2 以降 | Yoshiharu が観察、レポートは自動 |
| 5 | 本番で動く | デプロイ前 + 障害時 | dry-run + アラート |
