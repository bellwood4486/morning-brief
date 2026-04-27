# Design

## 1. アーキテクチャ概要

```
┌────────────────────────────────────────────────────────────────────┐
│  Modal Cron (21:30 UTC = 06:30 JST, 平日のみ)                       │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  Modal Function: digest_job                                         │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Modal Volume: ~/.hermes/                                     │   │
│  │   ├─ USER.md         (drift-adjusting user model)            │   │
│  │   ├─ MEMORY.md       (general knowledge)                     │   │
│  │   └─ skills.db       (SQLite, FTS5, auto-generated skills)   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Phase 1: feedback.collect_from_slack(yesterday)                   │
│           └─ Hermes に注入 (USER.md / skills 更新)                 │
│                                                                    │
│  Phase 2: gmail_client.fetch_unread(label, since=24h)              │
│           ↓                                                        │
│  Phase 3: summarize.summarize(emails) → Digest                     │
│           ↓ (Gemini 2.5 Flash, prompt from seeds/)                 │
│  Phase 4: formatter.to_block_kit(digest)                           │
│           ↓                                                        │
│           Notifier.send(blocks) → SlackNotifier                    │
│           ↓                                                        │
│  Phase 5: Hermes がログを観察してスキル自動生成・改善              │
│           └─ gmail_client.mark_processed(emails)                   │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────┴──────────────────────────┐
        ▼                                                     ▼
┌───────────────────┐                              ┌───────────────────┐
│ #newsletter-digest │                              │ #alerts           │
│ (ダイジェスト)     │                              │ (失敗時通知)      │
└───────────────────┘                              └───────────────────┘
        │
        ▼ 翌朝 Phase 1 で polling
   リアクション / ボタン / スレッド返信
```

外部依存:

| 外部 | 用途 | 認証 |
|------|------|------|
| Gmail API | ニュースレター取得、ラベル管理 | OAuth refresh token |
| Gemini API (AI Studio) | 日本語要約 | API key |
| Slack API | 配信、フィードバック収集 | Bot token |
| Modal | 実行環境、Cron、Volume、Secrets | CLI token (ローカルセットアップ時) |

## 2. コンポーネントの責務

### 2.1 `modal_app.py`
- Modal の cron デコレータでスケジュール定義
- Modal Image (依存パッケージ) の宣言
- Modal Volume / Secrets のマウント
- `digest_job` 関数の中で Phase 1-5 を順次呼び出す
- 各 Phase の例外を catch し、`#alerts` 通知 + 後続 Phase の継続判断

ここはオーケストレータ。ロジックは持たない。各モジュールを呼ぶだけ。

### 2.2 `src/digest/gmail_client.py`
- `fetch_unread(label, since) -> list[Email]`
- `mark_processed(emails)` (`Newsletter/Tech/Processed` ラベル付与)
- 受信専用。送信機能は実装しない。
- Email 構造体は `models.py` に定義 (`id`, `sender`, `subject`, `body_text`, `body_html`, `received_at`, `links`)

### 2.3 `src/digest/summarize.py`
- `summarize(emails) -> Digest`
- Gemini API (`google-genai`) を呼ぶ
- プロンプトは `seeds/summarize_prompt.md` から読み込む (ハードコード禁止)
- Digest 構造体は `models.py` に定義 (`tldr_items: list[TldrItem]`, `details: list[DetailItem]`, `generated_at`)

### 2.4 `src/digest/formatter.py`
- `to_block_kit(digest) -> list[dict]`
- Slack Block Kit の dict リストに変換
- リアクション促し絵文字 / ミュートボタンを各 detail block に付与
- ボタンの `action_id` には送信元情報を埋め込む (Phase 1 で復元できるように)

### 2.5 `src/digest/notifiers/`
- `base.py`: `Notifier` Protocol を定義 (`send(blocks) -> PostedMessage`, `collect_feedback(message_id) -> list[Feedback]`)
- `slack.py`: 唯一の現状実装。`slack_sdk` の import はこのファイル限定。

### 2.6 `src/digest/feedback.py`
- `collect_from_slack(yesterday_message_id) -> list[Feedback]`
- リアクション、ボタンクリック、スレッド返信を統合した `Feedback` リストを返す
- Hermes 側でどう扱うかはこのモジュールの関心外 (返すだけ)

### 2.7 `src/digest/hermes_bridge.py`
- Hermes との橋渡し
- `inject_feedback(feedbacks)`: フィードバックを Hermes に渡す
- `observe_session(session_log)`: ジョブ実行ログを渡し、スキル自動生成のトリガに
- 永続状態は Modal Volume にマウントされた `~/.hermes/` に Hermes 自身が書く

### 2.8 `seeds/`
- 永続化されない、リポジトリに置く初期データ
- `newsletter_digest.md`: agentskills.io 形式のスキル定義
- `summarize_prompt.md`: 要約プロンプト初期版
- `user_initial.md`: USER.md の初期コンテンツ (ユーザーの興味分野・読み方の癖)

## 3. データフロー (Phase 詳細)

### Phase 1: 前日フィードバック回収
```
yesterday_message_id = Hermes.get("last_digest_message_id")
feedbacks = feedback.collect_from_slack(yesterday_message_id)
hermes_bridge.inject_feedback(feedbacks)
```

`yesterday_message_id` は前日 Phase 4 完了時に Hermes に保存しておく。Hermes に持たせる理由は、Modal Volume の永続化に任せられるため (別途 KV ストア不要)。

### Phase 2: メール取得
```
emails = gmail_client.fetch_unread(label="Newsletter/Tech", since=timedelta(hours=24))
if not emails:
    notifier.send(blocks=empty_digest_blocks())
    return
```

空の場合も投稿する (silent failure 防止)。

### Phase 3: 要約
```
prompt = load_seed("summarize_prompt.md")
digest = summarize(emails, prompt=prompt, model="gemini-2.5-flash")
```

### Phase 4: 配信
```
blocks = formatter.to_block_kit(digest)
posted = notifier.send(blocks)
hermes.set("last_digest_message_id", posted.message_id)
```

### Phase 5: 後処理 + 学習
```
gmail_client.mark_processed(emails)
hermes_bridge.observe_session(session_log)
```

## 4. ADRs (Architectural Decision Records)

### ADR-001: インフラに Modal を採用

**決定**: Modal をホスト先とする。

**選択肢**:
- A. ローカル Mac (cron + 常駐)
- B. 安い VPS ($5/月)
- C. Cloud Run Jobs + Cloud Scheduler
- D. **Modal**

**理由**:
- ambient agent + serverless persistence というパラダイムを学ぶこと自体に価値がある。Modal Volume のハイバネート/起き上がりの体験は他で得にくい。
- アイドル中のコストがほぼゼロ。Modal の無料枠で完結する見込み。
- Hermes が Modal をネイティブバックエンドとしてサポートしている。

**トレードオフ**:
- GCP との統合の自然さは Cloud Run より低い (Vertex AI を使わない判断と表裏 / ADR-003 参照)。
- ベンダーロックがあるが、シングルユーザー前提なので許容。

### ADR-002: 配信媒体を Slack に統一 (Email から変更)

**決定**: 第一弾の配信先を Slack の個人用 workspace 新規作成とする。Email 配信は実装しない。

**経緯**:
- 当初は「最もシンプル」を理由に Email 配信から始める案だった。
- 議論の中で HITL の摩擦が低くないとフィードバックが続かない、という気付きから再検討。
- Email の返信で `mute: foo@bar.com` を書く UX と、Slack のリアクション 1 タップ + ミュートボタンの UX の差は実用上大きい。
- 通勤時の片手操作前提で、後者を選ぶ意義が学習目的の達成 (Sprint 2 のフィードバック観察) に直結する。

**実装コスト**: 当初想定より小さい。Email 返信パース実装が消え、リアクション/ボタンの構造化データ取得に置き換わる。差し引き同等かやや少。

### ADR-003: LLM を Vertex AI ではなく Gemini API (AI Studio) 直叩き

**決定**: Gemini API (AI Studio) を `google-genai` SDK で直接呼ぶ。Vertex AI 経由は使わない。

**理由**:
- Modal から使う場合、Vertex AI はサービスアカウント JSON が必要で、Modal Secrets への配置が煩雑。
- Gemini API は API キー 1 個で済み、Modal Secrets 1 個に収まる。
- OSS 参照実装としての再現性も、API キー 1 本のほうが圧倒的にシンプル。
- コストは同等。
- GCP は別件 (RAG パイプライン) で本格的に使えばよく、このプロジェクトで揃える必要はない。

### ADR-004: `Notifier` 抽象を 1 実装目から導入

**決定**: 第一弾が Slack のみであっても、`Notifier` Protocol を切り、`SlackNotifier` をその実装として実装する。

**理由**:
- 拡張性 (NFR-5) を実証するために、最初から抽象が機能している状態にしておく。
- 抽象を後から導入するリファクタは、テストカバレッジの薄い段階だと事故が起きやすい。
- `Notifier` Protocol は 5-10 行で書ける。コストはほぼゼロ。

**判断保留**:
- Hermes の Gateway 機能に乗せる案 (案 A) と自前抽象 (案 B) のどちらに最終的に寄せるかは、Sprint 3 で別 Notifier を追加するときに再判断する。

### ADR-005: プロンプトを `seeds/` に分離、コードにベタ書きしない

**決定**: 全プロンプトは `seeds/*.md` に Markdown で書き、実行時に読み込む。

**理由**:
- プロンプトは仕様の一部であり、コード差分よりプロンプト差分のほうがレビューしやすい。
- Hermes がスキルを Markdown で生成する流儀と一貫させる。
- A/B 実験 (プロンプト差し替え) がしやすい。

**強制**: `summarize.py` などにプロンプト相当の長文文字列リテラルが含まれていないかをアーキテクチャテストで検出する (`tests/architecture/test_prompts_in_seeds.py`)。

### ADR-006: HITL を Slack webhook ではなく翌朝 polling

**決定**: Slack のリアクション/ボタン/スレッド返信は、Modal Function 内から翌朝の Phase 1 で polling 取得する。Events API / Socket Mode は使わない。

**理由**:
- Events API (HTTPS webhook) は Modal web endpoint で受けられるが、ボタンクリックを即時処理する要件がない。
- Socket Mode は WebSocket 常駐が必要で、Modal の serverless 文脈と相反する。コスト優位性を失う。
- Polling は構造がシンプルで、Phase 1 として既存の Phase 構造に自然に乗る。
- 即時性が要らない (フィードバックは翌朝の生成で活きればよい) ため、polling のレイテンシは無問題。

### ADR-007: メール処理状態を Gmail ラベルで管理

**決定**: 処理済みメールは `Newsletter/Tech/Processed` ラベルで識別する。別途 DB は持たない。

**理由**:
- 状態管理を Gmail に寄せると、Modal Volume に状態を持たない/減らせる。
- 何が処理済みかを Gmail UI から直接確認・修正できる (デバッグ性)。
- ラベル付与は Gmail API で 1 コール。

### ADR-008: スケジュールは Modal Cron が起点 (Hermes 自前 cron は使わない)

**決定**: 平日 06:30 JST 起動は Modal の `modal.Cron` で行う。Hermes が持つ自然言語 cron 機能は使わない。

**理由**:
- Hermes 自前 cron はサーバ常駐前提。Modal の hibernate/wake モデルと相反する。
- 二重スケジューラは混乱の元。
- Modal Cron は宣言的で、コードを読めばスケジュールが自明。

### ADR-009: Gmail OAuth スコープは gmail.modify

**決定**: Gmail API に要求するスコープは `https://www.googleapis.com/auth/gmail.modify` のみ。

**理由**:
- `mark_processed` (`Newsletter/Tech/Processed` ラベル付与, ADR-007) にはラベル変更権限が必要。`gmail.readonly` では `users.messages.modify` API が呼べない。
- `gmail.send` はこのサービスの責務外 (CLAUDE.md「送信に Gmail を使わない」)。
- フルアクセス (`https://mail.google.com/`) は最小権限原則に反する。

**影響**: OAuth 認可画面に「メールの読み取り、構成、削除、送信」と表示されるが (Google 側の固定表記)、実際に送信は行わない。利用者への説明は `docs/setup.md` (T1.13) で補足する。

## 5. 拡張ポイント

### 5.1 配信先の追加 (Notifier)
1. `src/digest/notifiers/<name>.py` に `Notifier` Protocol を実装する新クラスを書く。
2. `config.yaml` の `notifiers:` セクションにエントリ追加。
3. 必要な秘匿情報を Modal Secrets に登録。
4. 動作確認: `modal run modal_app.py::digest_job --dry-run` で対象 Notifier がエラーなく `send` を呼ぶか確認。

コア (`modal_app.py`, 各 Phase) は変更しない。

### 5.2 ソースの追加 (Gmail 以外)
1. `src/digest/sources/<name>.py` を作り、`Source` Protocol を実装 (`fetch_unread() -> list[Email]`)。
   - 注: `Source` Protocol は Sprint 1 では未抽出。Sprint 3 で必要になった時点で `gmail_client` から抽出する。
2. Phase 2 を該当 Source に切り替え or 並列実行に変更。

### 5.3 別エージェントの追加 (例: カレンダー要約)
1. 新リポジトリではなく、同 workspace の別 channel を使う形を推奨。
2. Modal Function を別途作り、別の cron を持たせる。Volume は別パス (`~/.hermes-cal/`) に分離。
3. これにより本プロジェクトのスコープが膨らまない。

## 6. 障害時の挙動

| 障害箇所 | 期待挙動 |
|---------|---------|
| Phase 1 失敗 (フィードバック取得) | warning ログ。Phase 2 以降は継続 (今日のダイジェストは届く)。 |
| Phase 2 が空 (対象メールなし) | `#newsletter-digest` に「本日は対象メールなし」を投稿。Phase 5 はスキップ。 |
| Phase 3 失敗 (Gemini エラー) | `#alerts` に通知。再実行は手動。 |
| Phase 4 失敗 (Slack 送信エラー) | `#alerts` に通知。Gemini 出力は Modal の stdout にログとして残す。 |
| Modal Function 自体が起動しない | 検知不可 (Modal の死活監視に依存)。割り切り。 |

`#alerts` channel への通知も Slack なので、Slack 自体が落ちると気付けない。これは許容する (NG: 厳密な SLA)。

## 7. 命名・型方針

- 型ヒントは厳格に書く (`mypy --strict` 相当)。
- ドメインモデルは `src/digest/models.py` に集約 (`Email`, `Digest`, `TldrItem`, `DetailItem`, `Feedback`, `PostedMessage`)。
- ドメインモデルは pydantic v2 `BaseModel` を採用。共通基底 `_StrictModel` に `extra="forbid"`, `frozen=True`, `str_strip_whitespace=True` を集約。`datetime` は aware UTC のみ許可 (naive は `ValidationError`)。永続化やシリアライズは `model_dump_json()` / `model_validate_json()` で行う。
- 関数名は動詞始まり (`fetch_unread`, `summarize`, `to_block_kit`)。
- Phase の関数は副作用を持つので、戻り値を持つ関数 (純粋寄り) と分けて意図を表現する。

## 8. テスト戦略の概要

詳細は `docs/quality.md` 参照。設計レベルの方針だけ:

- Gmail / Gemini / Slack の外部 API 呼び出しは全て差し替え可能なクライアントを介する (テスト時にモック注入)。
- Phase 単位の統合テストを書く (各 Phase の入出力契約)。
- Modal Function 全体の e2e は手動 `--dry-run` 確認に任せる (自動化は過剰)。
