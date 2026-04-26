# CLAUDE.md

`morning-brief` は、Gmail に届く英語のテック系ニュースレターを Gemini で日本語要約し、平日朝 6:30 に Slack へ配信する個人向け ambient agent です。Modal 上でサーバーレスに動作し、Hermes Agent によって学習・成長します。

このファイルは Claude Code がこのリポジトリで作業する際の運用マニュアルです。設計判断の背景は `docs/design.md`、要件は `docs/requirements.md`、タスク分解は `docs/tasks.md`、検証手順は `docs/quality.md` を参照してください。

## 主要な決定事項

| 項目 | 決定 |
|------|------|
| 配信媒体 | Slack (個人用 workspace 新規作成) |
| 対象判別 | Gmail ラベル `Newsletter/Tech` |
| 要約構造 | 2段構え (TL;DR 3-5本 + 詳細1メール1ブロック) |
| 実行タイミング | 平日 06:30 JST、前24h分を1バッチ |
| LLM | Gemini 2.5 Flash (AI Studio API key) |
| インフラ | Modal (Cron + Volume + Secrets) |
| HITL | Slack リアクション/ボタン/スレッド返信、翌朝 polling |
| 配信抽象 | `Notifier` Protocol (第一実装は `SlackNotifier`) |
| プロンプト | 初期版は手書き seed → Hermes が育てる |
| 秘匿情報 | Modal Secrets。リポジトリには `.env.example`, `config.example.yaml` のみ |

判断の経緯は `docs/design.md` の ADR セクション参照。

## ディレクトリ構成

```
morning-brief/
├── CLAUDE.md                       # このファイル
├── README.md                       # OSS 読み手向け (Sprint 1 終盤に作成)
├── pyproject.toml                  # uv 管理
├── modal_app.py                    # Modal エントリ (cron + function)
├── src/digest/
│   ├── __init__.py
│   ├── gmail_client.py             # 受信専用 (送信に使わない)
│   ├── summarize.py                # Gemini 呼び出し、プロンプトは seeds/ から読む
│   ├── formatter.py                # Block Kit 生成
│   ├── feedback.py                 # 前日リアクション/返信のパース
│   ├── hermes_bridge.py            # Hermes との橋渡し
│   └── notifiers/
│       ├── __init__.py
│       ├── base.py                 # Notifier Protocol
│       └── slack.py                # 唯一の現状実装
├── seeds/
│   ├── newsletter_digest.md        # Hermes 初期スキル定義
│   ├── summarize_prompt.md         # 要約プロンプト初期版
│   └── user_initial.md             # USER.md 初期コンテンツ
├── scripts/
│   ├── check.sh                    # 層1+3 一括検証
│   ├── bootstrap_oauth.py          # 初回 Gmail refresh_token 取得 (ローカル実行)
│   └── weekly_report.py            # 層4 学習観察レポート (Sprint 2)
├── tests/
│   ├── unit/
│   ├── integration/                # 外部 API モック
│   └── architecture/               # 設計遵守テスト
├── config.example.yaml             # ラベル名・実行時刻など
├── .env.example                    # 環境変数テンプレ
├── .gitignore
└── docs/
    ├── requirements.md             # WHAT / WHY
    ├── design.md                   # HOW it's built + ADRs
    ├── tasks.md                    # Sprint 分解
    ├── quality.md                  # 検証ハーネス定義
    ├── agent-design.md             # Hermes エージェント仕様 (Sprint 1 中に作成)
    ├── setup.md                    # 運用手順 (Sprint 1 終盤に作成)
    └── observation.md              # 学習観察ログ (Sprint 1 完了時に追加)
```

## やってはいけないこと

1. **秘匿情報をコミットしない**: API キー、refresh token、bot token は Modal Secrets で管理。`.env` は `.gitignore` 済み。コミット前に `gitleaks` 相当のチェックが入る (`scripts/check.sh`)。
2. **Notifier 抽象を飛ばさない**: `slack_sdk` の import は `src/digest/notifiers/slack.py` 以外で禁止。アーキテクチャテストで検出する。
3. **Hermes の永続状態に直接書き込まない**: `~/.hermes/` は Modal Volume 経由でのみアクセス。`hermes_bridge.py` を介す。
4. **プロンプトをコードにベタ書きしない**: 全プロンプトは `seeds/*.md` から読み込む。
5. **Vertex AI を使わない**: Gemini API 直叩き (`google-genai` SDK) で統一。理由は ADR-003。
6. **送信に Gmail を使わない**: Gmail API は受信専用。配信は Slack 経由 (将来 Notifier 追加で拡張)。
7. **常駐サーバ前提の機能を使わない**: Slack Socket Mode、Hermes 自前 cron は不可。Modal Cron が唯一の起点。
8. **暗黙の決定をしない**: 設計に書かれていない判断が必要になったら、実装する前に確認を取る。

## 開発コマンド

```bash
# 依存セットアップ
uv sync

# Lint / Format / Type
uv run ruff check .
uv run ruff format .
uv run mypy src/

# テスト
uv run pytest tests/unit/                       # 高速、外部依存なし
uv run pytest tests/integration/ -m "not external"  # モック前提の統合
uv run pytest tests/architecture/               # 設計遵守

# 一括検証 (コミット前に必ず実行)
./scripts/check.sh

# Modal でのドライラン (送信せず最終 Markdown を stdout に出す)
modal run modal_app.py::digest_job --dry-run

# Modal 本番実行 (手動トリガ)
modal run modal_app.py::digest_job
```

## 検証ルーチン

コミット前に必ず以下を実行:

```bash
./scripts/check.sh
```

これは以下を実行します(詳細は `docs/quality.md`):

- 層1: ruff (lint + format), mypy (型), pytest (unit + integration)
- 層3: アーキテクチャテスト (境界破り検出、秘匿情報検出)

各タスクの完了判定は `docs/tasks.md` の Given-When-Then 形式の受入条件で行います。**受入条件を満たすテストが通るまで、そのタスクは「完了」ではありません**。「動いた」「実装した」だけでは不十分です。

## 実装方針

- **言語**: Python 3.11+。型ヒントは厳格に書く (`mypy --strict` 相当)。
- **パッケージマネージャ**: uv。
- **ドメインモデル**: dataclass または pydantic。`Email`, `Digest`, `DigestItem`, `Feedback` などの型を `src/digest/models.py` に集約。
- **エラー処理**: 各 Phase は独立して失敗可能にする。Phase 2 (Gmail 取得) が空でも Phase 4 (Slack 送信) は「本日は対象メールなし」を投稿する。silent failure を起こさない。
- **ロギング**: 標準 `logging`。Modal の stdout に流す。

## 迷ったとき

- 設計判断の理由 → `docs/design.md` の ADR セクション
- 何をするか → `docs/tasks.md` (現在の Sprint)
- 機能要件・非機能要件 → `docs/requirements.md`
- どう検証するか → `docs/quality.md`
- 上記に書かれていない判断は、暗黙にせず確認を取る
