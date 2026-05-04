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
- リポジトリに秘匿情報が含まれていない (`uv run pre-commit run --all-files` がグリーン)。
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
- [x] T1.10 Modal アプリ本体
- [x] T1.11 Seeds 初期版
- [x] T1.12 検証スクリプトと CI 用 hook
- [x] T1.13 ドキュメント (agent-design.md, setup.md)
- [x] T1.14 README.md

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
- `seeds/newsletter_digest.md`: agentskills.io 形式のスキル定義 (Sprint 2 / ADR-012 で削除済み)
- `seeds/user_initial.md`: USER.md の初期コンテンツ

**注記**: これらの初期版はユーザーが叩き台を書く想定。Claude Code はテンプレを用意し、ユーザーがレビュー・修正する。

**受入条件**:

- Given: 3 ファイルが存在する
- When: `summarize.py` から `load_seed("summarize_prompt.md")` で読める
- Then: ファイル内容が文字列で取得できる
- And: agent-design.md にこれら seed の方針が文書化されている (Sprint 1 終盤の T1.13 で対応)

#### T1.12 コマンドランナー / 開発前提ツール / secrets check

**作業**: `justfile` (コマンドランナー) + 開発前提ツール (`mise`) + secrets check (gitleaks 相当)。

- (済) `justfile`: ruff / mypy / pytest / secrets を just ターゲットに集約。`just check` で一括実行。
- (済) `.mise.toml`: python (`3.11`) / uv / just / gitleaks を宣言。`mise install` で一括導入。
- (済) secrets check: `.gitleaks.toml` で `tests/` と偽トークンを allowlist。gitleaks (未インストール時は grep フォールバック)。`tests/architecture/test_no_secrets_in_code.py` を pytest 層にも追加。

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

#### Sprint 1 完了後の追加作業

T1.14 完了後、Sprint 1 完了基準の実成立や運用着手に伴って発生した修正・改善。

- [x] #20 dry-run のバグ修正 (Phase 3 logging の Digest attribute reference)
- [x] #23 Slack `chat.postMessage` に text fallback を追加
- [x] #25 LangSmith + Logfire によるトレーシングを追加
- [x] #26 `just deploy` ターゲット追加 (Modal Cron 有効化用)
- [x] #27 Slack チャンネルを ID 指定に切り替え、`config.yaml` を untrack
- [x] #28 `logging`→Logfire ブリッジ追加 (エラーパスを Logfire 上で観測可能に)

---

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

## Sprint 2: Hermes 廃止 + 境界B 移行 + USER.md 自動更新ループ

### 目的

Hermes を廃止し (ADR-012)、PydanticAI + Logfire 統一 (ADR-013) + USER.md Volume 管理 (ADR-015) へ移行する。
feedback → USER.md 自動更新 → Slack 通知のサイクルを動かし、ambient agent の学習目的を達成する。

### タスク

#### 進捗

- [x] T2.1 ButtonFeedback 廃止 / 🔇 リアクション統一 / formatter からミュートボタン削除
- [x] T2.2 Hermes 関連コード削除 (`hermes_bridge.py` / `seeds/newsletter_digest.md` / 関連テスト / アーキテクチャテスト調整)
- [x] T2.3 PydanticAI 導入 + LangSmith 削除 + Logfire 1 本化 (`observability.py` / `summarize.py` 書き換え)
- [x] T2.4 `state_store.py` + `user_md_updater.py` 新規実装 (feedback.jsonl 蓄積 + Gemini diff 生成)
- [x] T2.5 USER.md / MEMORY.md の Modal Volume 直接更新 + Slack 通知 (ADR-015; GitHub PR フローを廃止)

### Sprint 2 完了基準

- [x] T2.1 〜 T2.5 がマージされている
- [ ] `just dry-run` で Phase 1 (feedback.jsonl 追記) と Phase 5 (USER.md diff 生成ログ + dry_run 出力) が出る
- [ ] `just check` がグリーン

---

#### T2.5 USER.md / MEMORY.md の Modal Volume 直接更新 + Slack 通知

**作業**:

- `src/digest/userdoc_store.py` 新規実装 (bootstrap / read / write_with_snapshot + スナップショット世代管理)
- `src/digest/userdoc_notifier.py` 新規実装 (unified diff + Block Kit 組み立て)
- `seeds/memory_initial.md` 新規 (空テンプレ)
- `src/digest/user_md_updater.py`: `update_if_ready` signature 変更 (`userdoc_store` 引数追加、戻り値 `UserMdDiff | None`、`dry_run` 引数削除)
- `src/digest/state_store.py`: `rotate_feedback()` 追加
- `modal_app.py`: bootstrap 呼び出しと Phase 5 結線
- `config.example.yaml`: `slack.userdoc_channel` 追加

**受入条件**:

- Given: Modal Volume が空 (USER.md / MEMORY.md なし)
  When: `digest_job` を実行
  Then: Volume に `USER.md` が `seeds/user_initial.md` の内容で、`MEMORY.md` が `seeds/memory_initial.md` の内容で生成される
  And: 2 回目の実行では既存ファイルが上書きされない (再起動冪等)

- Given: `feedback.jsonl` に 5 件以上の feedback / Volume に USER.md あり
  When: `update_if_ready(feedback_log_path, userdoc_store)` を呼ぶ
  Then: 戻り値は `UserMdDiff` インスタンス
  And: Volume の USER.md / MEMORY.md / feedback.jsonl に副作用が発生しない

- Given: feedback < 5 件
  When: `update_if_ready(...)` を呼ぶ
  Then: `None` を返す

- Given: `diff.user_md_content` / `diff.memory_md_content` が現行 Volume の内容と byte-equal
  When: `userdoc_store.write_with_snapshot(...)` を呼ぶ
  Then: 戻り値が `None`。Volume と snapshots に副作用なし

- Given: feedback ≥ 5 / Gemini diff が現行と異なる / Volume 書き込み成功
  When: `digest_job(dry_run=False)` を実行
  Then: Volume の USER.md / MEMORY.md が更新される
  And: `state/snapshots/` に新しいスナップショットが追加される
  And: Slack の userdoc_channel に change_summary + unified diff が投稿される
  And: `feedback.jsonl` が archived 名にリネームされる

- Given: 同条件で dry_run=True
  When: `digest_job(dry_run=True)` を実行
  Then: stdout に change_summary と diff hunks の冒頭が出力される
  And: Volume / snapshot / Slack / feedback.jsonl は変更されない

- Given: `just check` を実行
  Then: lint / fmt / type / test / test-arch / md-lint がすべてグリーン

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

---

### Sprint 3+ 想定 (本リスト外)

以下は Sprint 3 の Notifier 拡張とは別フェーズで扱う想定の課題:

- **プロンプト改善ループ**: `seeds/summarize_prompt.md` の改善案を Gemini が提案 → Slack 通知 → 人間が手動適用 (Sprint 4 相当)
- **観察ログ整備**: `scripts/weekly_report.py` でフィードバック統計 / USER.md 更新履歴 / LLM コストを週次 Slack 投稿
