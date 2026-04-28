# Tasks

このドキュメントは Sprint ごとのタスク分解と、各タスクの受入条件を定義する。**受入条件を満たすテストが通るまで、そのタスクは「完了」ではない**。

## Sprint 1: MVP (動くものを作る)

### 目的

- 通勤時のダイジェスト読書を成立させる。
- Modal / Hermes / Gemini / Slack / Gmail の結線を確認する。
- HITL は最小限 (リアクション/ボタンの収集経路が動くところまで。Hermes への反映は Sprint 2)。

### Sprint 1 完了基準 (全体)

- 平日朝 06:30 JST に `#newsletter-digest` にダイジェストが自動投稿される。
- ダイジェストは TL;DR + 詳細の 2 段構え。
- 各記事ブロックに 👍/👎/🔥 リアクション促し + ミュートボタンが付いている。
- リポジトリに秘匿情報が含まれていない (`just secrets` がグリーン、T1.12 残部分で追加予定)。
- `just check` 全体がグリーン。

### タスク一覧

#### 進捗

- [x] T1.1 プロジェクトセットアップ
- [x] T1.2 ドメインモデル定義
- [x] T1.3 Notifier Protocol
- [x] T1.4 Slack Notifier 実装
- [x] T1.5 Gmail クライアント (受信 + 処理済みラベル)
- [x] T1.6 OAuth bootstrap スクリプト
- [x] T1.7 要約モジュール (Gemini)
- [x] T1.8 Block Kit フォーマッタ
- [x] T1.9 Hermes Bridge (最小実装)
- [ ] T1.10 Modal アプリ本体
- [x] T1.11 Seeds 初期版
- [ ] T1.12 検証スクリプトと CI 用 hook
- [ ] T1.13 ドキュメント (agent-design.md, setup.md)
- [ ] T1.14 README.md

---

#### T1.1 プロジェクトセットアップ

**作業**:

- `pyproject.toml` (uv 管理、Python 3.11+)
- 依存: `modal`, `google-genai`, `slack_sdk`, `google-api-python-client`, `google-auth-oauthlib`, `pydantic`, `pyyaml`
- dev 依存: `ruff`, `mypy`, `pytest`, `pytest-mock`
- `.gitignore`, `.env.example`, `config.example.yaml`
- `src/digest/__init__.py`, `src/digest/notifiers/__init__.py`
- `tests/{unit,integration,architecture}/__init__.py`

**受入条件**:

- Given: clone 直後の状態
- When: `uv sync` を実行
- Then: 依存がインストールされ、`uv run python -c "import digest"` が成功する
- And: `uv run ruff check .` がグリーン
- And: `uv run mypy src/` がグリーン (まだ src/ がほぼ空でも OK)

#### T1.2 ドメインモデル定義

**作業**: `src/digest/models.py` を作る。

**含めるもの**:

- `Email` (id, sender, subject, body_text, body_html, received_at, links: list[str])
- `TldrItem` (title_ja, summary_ja, source_url, source_email_id)
- `DetailItem` (sender, subject_ja, points: list[str], glossary: dict[str, str], source_url, source_email_id)
- `Digest` (tldr_items, details, generated_at)
- `Feedback` (kind: Literal["reaction", "button", "thread_reply"], target_email_id, value, raw)
- `PostedMessage` (channel, message_id, posted_at)

**受入条件**:

- Given: `models.py` が実装されている
- When: `tests/unit/test_models.py` を実行
- Then: 各モデルが期待値で初期化でき、不正値で `ValidationError` を出す
- And: `mypy --strict src/digest/models.py` がグリーン

#### T1.3 Notifier Protocol

**作業**: `src/digest/notifiers/base.py` に `Notifier` Protocol。

```python
class Notifier(Protocol):
    def send(self, blocks: list[dict]) -> PostedMessage: ...
    def collect_feedback(self, message_id: str) -> list[Feedback]: ...
```

**受入条件**:

- Given: Protocol が定義されている
- When: 別ファイルから `from digest.notifiers.base import Notifier` できる
- Then: import エラーなし
- And: アーキテクチャテスト `test_notifier_protocol_minimal` で、Protocol が 2 メソッドのみを持つことを検証

#### T1.4 Slack Notifier 実装

**作業**: `src/digest/notifiers/slack.py`。

- `slack_sdk` を import (このファイル限定)。
- `send(blocks)` で `chat.postMessage` を呼び、`PostedMessage` を返す。
- `collect_feedback(message_id)` で `reactions.get` + `conversations.replies` + (ボタンクリックの履歴は Phase 4 で別途記録した `actions.log` を読む)。

**受入条件**:

- Given: モック化された Slack Web Client
- When: `SlackNotifier.send(blocks=[...])` を呼ぶ
- Then: `chat.postMessage` がチャンネル `#newsletter-digest`、blocks 引数で呼ばれる
- And: 返り値の `PostedMessage.message_id` は API レスポンスの `ts` フィールド
- Given: モック化された Slack で前日のメッセージにリアクションとスレッド返信あり
- When: `collect_feedback(message_id)` を呼ぶ
- Then: 各リアクション・各返信が `Feedback` として返る

#### T1.5 Gmail クライアント (受信 + 処理済みラベル)

**作業**: `src/digest/gmail_client.py`。

- `fetch_unread(label, since) -> list[Email]`
- `mark_processed(emails)` (`Newsletter/Tech/Processed` ラベル付与)
- OAuth 認証は Modal Secrets から `gmail_oauth.json` (refresh_token 入り) を読む

**受入条件**:

- Given: モック化された Gmail API、`Newsletter/Tech` ラベル付き未読 3 件 (24h 以内)
- When: `fetch_unread(label="Newsletter/Tech", since=timedelta(hours=24))` を呼ぶ
- Then: 3 件の `Email` が返る
- And: ラベル違いのメールは含まれない
- And: 24h 超のメールは含まれない
- And: HTML 本文があれば `body_html`、なければ `body_text` のみ
- Given: `mark_processed(emails)` を呼ぶ
- Then: 各メールに `Newsletter/Tech/Processed` ラベル追加 API が呼ばれる

#### T1.6 OAuth bootstrap スクリプト

**作業**: `scripts/bootstrap_oauth.py` (ローカル実行)。

- Desktop app OAuth flow で refresh_token を取得
- 取得後、Modal Secrets に登録するコマンドを stdout に表示

**受入条件**:

- Given: Google Cloud Console で OAuth client (Desktop) を作成済み、`credentials.json` がカレントにある
- When: `uv run python scripts/bootstrap_oauth.py` を実行
- Then: ブラウザが開いて OAuth 認可フローが走る
- And: 完了後 `gmail_oauth.json` がカレントに生成される
- And: stdout に `modal secret create gmail-oauth ...` のコマンドが表示される

#### T1.7 要約モジュール (Gemini)

**作業**: `src/digest/summarize.py`。

- `summarize(emails, prompt, model="gemini-2.5-flash") -> Digest`
- プロンプトは `seeds/summarize_prompt.md` から読み込む (`load_seed("summarize_prompt.md")`)
- Gemini からの JSON レスポンスを `Digest` 型にパース

**受入条件**:

- Given: `seeds/summarize_prompt.md` が存在する、モック化された Gemini クライアント、ダミーの 3 件メール
- When: `summarize(emails, prompt, model)` を呼ぶ
- Then: Gemini が 1 度だけ呼ばれ、プロンプトに seed の内容が含まれる
- And: 戻り値は `Digest` 型で `tldr_items` に 3-5 件、`details` に 3 件含む
- Given: コード内に長文文字列リテラル (例: 200 文字以上の英文/日本語) が無い
- When: `tests/architecture/test_prompts_in_seeds.py` を実行
- Then: グリーン

#### T1.8 Block Kit フォーマッタ

**作業**: `src/digest/formatter.py`。

- `to_block_kit(digest) -> list[dict]`
- ヘッダーブロック (日付)
- TL;DR セクション (各項目に title, summary, リンク)
- 詳細セクション (各項目に points, glossary, リンク)
- 各 detail block に 👍/👎/🔥 のリアクション促し note と `[ミュート]` ボタン

**受入条件**:

- Given: ダミーの `Digest`
- When: `to_block_kit(digest)` を呼ぶ
- Then: 戻り値は Block Kit の dict のリスト
- And: 各 detail block に `accessory` または `actions` として button が含まれる
- And: button の `action_id` に元メールの sender が埋め込まれている (Phase 1 でミュート対象を復元するため)
- And: Slack Block Kit Builder で valid と判定される (オプション: 検証用 lib があれば)

#### T1.9 Hermes Bridge (最小実装)

**作業**: `src/digest/hermes_bridge.py`。

- Sprint 1 段階では「永続状態のロード/セーブ」と「セッションログの保存」だけ動けばよい。
- `inject_feedback`, `observe_session` は実装するが、Hermes が反映するロジックは Sprint 2 で詳細化。
- `last_digest_message_id` の get/set はファイル (`~/.hermes/state/last_digest.json`) で実装。

**受入条件**:

- Given: Modal Volume に相当するテンポラリディレクトリ
- When: `set_last_message_id("ts123")` → `get_last_message_id()`
- Then: `"ts123"` が返る
- And: 別プロセスで再ロードしても永続している

#### T1.10 Modal アプリ本体

**作業**: `modal_app.py`。

- `modal.App("morning-brief")`
- Modal Image (依存パッケージインストール、`seeds/` を image にコピー)
- Modal Volume (`/root/.hermes/`) と Secrets (`gmail-oauth`, `gemini-api-key`, `slack-bot-token`) のマウント
- `@app.function(schedule=modal.Cron("30 21 * * 1-5"))` で `digest_job` 定義
- `digest_job(dry_run: bool = False)` の中で Phase 1-5 を順に実行
- 各 Phase の例外は catch、`#alerts` 通知、後続 Phase の継続判断
- `dry_run=True` の場合、Phase 4 の Slack 送信を stdout への print に置き換え

**受入条件**:

- Given: 全モジュールが実装済み
- When: `modal run modal_app.py::digest_job --dry-run` をローカルから実行
- Then: 例外なく完了し、最終 Markdown が stdout に出る
- And: Slack には何も投稿されていない
- And: Gmail のラベルも変更されていない (`mark_processed` も dry_run 対応)
- Given: `dry_run=False`
- When: 同様に実行
- Then: `#newsletter-digest` に投稿される
- And: 対象メールに `Newsletter/Tech/Processed` ラベルが付く

#### T1.11 Seeds 初期版

**作業**: `seeds/` 配下 3 ファイル。

- `seeds/summarize_prompt.md`: 要約プロンプト初期版
- `seeds/newsletter_digest.md`: agentskills.io 形式のスキル定義
- `seeds/user_initial.md`: USER.md の初期コンテンツ

**注記**: これらの初期版はユーザーが叩き台を書く想定。Claude Code はテンプレを用意し、ユーザーがレビュー・修正する。

**受入条件**:

- Given: 3 ファイルが存在する
- When: `summarize.py` から `load_seed("summarize_prompt.md")` で読める
- Then: ファイル内容が文字列で取得できる
- And: agent-design.md にこれら seed の方針が文書化されている (Sprint 1 終盤の T1.13 で対応)

#### T1.12 コマンドランナーと secrets check

**作業**: `justfile` (コマンドランナー) + secrets check (gitleaks 相当)。

- (済) `justfile`: ruff / mypy / pytest を just ターゲットに集約。`just check` で一括実行。
- (未) secrets check: gitleaks バイナリまたは grep フォールバックで API キー風文字列を検出。`just secrets` ターゲットとして追加予定。

**受入条件**:

- Given: 変更がない健全な状態
- When: `just check` を実行
- Then: 全て通り終了コード 0

#### T1.13 ドキュメント (agent-design.md, setup.md)

**作業**:

- `docs/agent-design.md`: Hermes エージェント仕様。seed の方針、フィードバック反映ルール (Sprint 2 で詳細化する旨を明記)。
- `docs/setup.md`: 初回セットアップ手順 (Modal, Slack App, Gmail OAuth, Gemini API key, Modal Secrets 登録)。各ステップに「成功確認コマンド」を併記。

**受入条件**:

- Given: 別 PC でこのリポジトリを clone
- When: `docs/setup.md` の手順に沿って進める
- Then: 詰まるポイントなく Sprint 1 完了基準まで再現できる (実機検証は実装後にユーザーが行う)

#### T1.14 README.md

**作業**: OSS 読み手向けの第一印象。

- 1 行説明
- 何が嬉しいか (3 行)
- アーキテクチャ図 (`docs/design.md` から抜粋)
- セットアップへのリンク (`docs/setup.md`)
- ライセンス (MIT)

**受入条件**:

- Given: GitHub のトップに表示される
- When: 知らない人が読む
- Then: このプロジェクトが何をするか、誰向けかが 30 秒で理解できる

### Sprint 1 タスク間の依存関係

```text
T1.1 (setup)
  ├─ T1.2 (models)
  │    ├─ T1.3 (Notifier Protocol)
  │    │    └─ T1.4 (SlackNotifier)
  │    ├─ T1.5 (Gmail client) ── T1.6 (bootstrap_oauth)
  │    ├─ T1.7 (summarize) ── T1.11 (seeds)
  │    ├─ T1.8 (formatter)
  │    └─ T1.9 (hermes_bridge)
  │         └─ T1.10 (modal_app) ←── 全部の合流点
  ├─ T1.12 (justfile + secrets) (並行可能)
  └─ T1.13, T1.14 (docs) (T1.10 完了後)
```

### Sprint 1 着手順

推奨順 (依存と難易度を考慮):

1. T1.1 → T1.2 → T1.3 → T1.4 (配信側を先に固める)
2. T1.6 → T1.5 (OAuth が動かないと先に進めない)
3. T1.11 (seeds の叩き台) → T1.7 (要約)
4. T1.8 → T1.9
5. T1.10 (合流)
6. T1.12 → T1.13 → T1.14 (仕上げ)

## Sprint 2: HITL ループ + ambient agent 観察

### 目的 (学習目的の本丸)

フィードバックが Hermes の USER.md / skill に反映されるサイクルを作り、観察する。

### タスク (概要、Sprint 1 完了後に詳細化)

#### 進捗

- [ ] T2.1 `feedback.collect_from_slack` 完全実装 (リアクション + ボタン + スレッド返信を統合)
- [ ] T2.2 Hermes へのフィードバック反映ロジック (`hermes_bridge.inject_feedback` の本実装)
- [ ] T2.3 Hermes のスキル自動生成を観察するためのログ収集
- [ ] T2.4 `scripts/weekly_report.py` (USER.md 差分、スキル数推移、フィードバック統計、コスト)
- [ ] T2.5 `docs/observation.md` への観察ログ蓄積 (運用フェーズ)

### Sprint 2 完了基準

- HITL フィードバックが Hermes に反映される経路が動いている。
- `docs/observation.md` に 2 週間以上の観察ログがある。
- `scripts/weekly_report.py` が日曜に Slack へ自動投稿する。
- USER.md 初期状態と現在の差分が明確で、学習が起きている証跡がある。

## Sprint 3: 拡張性検証

### 目的

`Notifier` 抽象が機能していることを実地検証する。

### タスク (概要、選択式)

以下のうち 1 つを選んで実装:

#### 進捗

- [ ] 候補 A: Telegram 通知追加 (`TelegramNotifier`)
- [ ] 候補 B: 別ソース追加 (RSS フィード等。`Source` Protocol を抽出するリファクタを伴う)
- [ ] 候補 C: 別エージェント追加 (カレンダー朝サマリ。同 workspace の別 channel)

### Sprint 3 完了基準

- 選んだ拡張が、コア (`modal_app.py`, 各 Phase の制御フロー) を変更せずに動いている。
- 拡張作業のログが `docs/observation.md` または別ファイルに残り、抽象が機能したか・しなかったかの評価がある。
