# Design

## 1. アーキテクチャ概要

```text
┌────────────────────────────────────────────────────────────────────┐
│  Modal Cron (21:30 UTC = 06:30 JST, 毎日)                           │
└────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  Modal Function: digest_job                                         │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Modal Volume: /root/.brief/                                  │   │
│  │   └─ state/last_digest.json  (前日の Slack message_id)       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  Phase 1: notifier.collect_feedback(yesterday_msg_id)              │
│           └─ state_store.append_feedback(feedbacks)                │
│              → /root/.brief/feedback.jsonl に追記                  │
│                                                                    │
│  Phase 2: gmail_client.fetch_unread(label, since=24h)              │
│           ↓                                                        │
│  Phase 3: summarize.summarize(emails) → Digest                     │
│           ↓ (Gemini / PydanticAI, prompt from seeds/)              │
│  Phase 4: formatter.to_block_kit(digest)                           │
│           ↓                                                        │
│           Notifier.send(blocks) → SlackNotifier                    │
│           ↓                                                        │
│  Phase 5: user_md_updater.update_if_ready()                        │
│           └─ Gemini が seeds/USER.md diff を生成 → GitHub PR 化    │
│              → gmail_client.mark_processed(emails)                 │
└────────────────────────────────────────────────────────────────────┘
                    │                    │
          ┌─────────┘           ┌────────┘
          ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│ #newsletter-     │  │ #alerts          │
│ digest           │  │ (失敗時通知)      │
│ (ダイジェスト)    │  └──────────────────┘
└──────────────────┘
        │
        ▼ 翌朝 Phase 1 で polling
   リアクション (👍/👎/🔥/🔇) / スレッド返信
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
- リアクション促し (👍/👎/🔥/🔇) を各 detail block の context に付与
- `[ミュート]` ボタンは廃止済み (ADR-012)。ミュート意思は 🔇 リアクションで表明する

### 2.5 `src/digest/notifiers/`

- `base.py`: `Notifier` Protocol を定義 (`send(blocks) -> PostedMessage`, `collect_feedback(message_id) -> list[Feedback]`)
- `slack.py`: 唯一の現状実装。`slack_sdk` の import はこのファイル限定。

### 2.6 `src/digest/notifiers/slack.py` (フィードバック収集)

- フィードバック収集は `Notifier.collect_feedback(message_id)` に統合済み (Sprint 1 で `SlackNotifier` に実装)
- `Feedback` 型は `models.py` に集約: `Feedback = ReactionFeedback | ThreadReplyFeedback`
- `ReactionFeedback`: 絵文字リアクション (👍/👎/🔥/🔇 等)
- `ThreadReplyFeedback`: スレッド返信 (自由記述)
- ButtonFeedback は廃止済み (ADR-012 参照)。Slack interactivity webhook を使わない方針と整合

### 2.7 `src/digest/state_store.py` と `src/digest/user_md_updater.py`

旧 `hermes_bridge.py` を T2.2 で削除済み。責務は T2.4 で 2 ファイルに分割して再実装する。

**`state_store.py`**:

- `get/set_last_message_id()`: Modal Volume の `state/last_digest.json` に前日 Slack `ts` を原子的に読み書き (一時ファイル + `os.replace`)
- `append_feedback(feedbacks)`: Phase 1 で収集したフィードバックを `/root/.brief/feedback.jsonl` に追記 (JSONL 形式、累積)

**`user_md_updater.py`**:

- `update_if_ready(feedback_log_path, userdoc_store) -> UserMdDiff | None`: feedback.jsonl に一定量のフィードバックが蓄積されたら Gemini (PydanticAI 経由) に USER.md / MEMORY.md の差分を生成する。副作用なし — Volume への書き込みは呼び出し側 (`modal_app.py`) の責務 (ADR-015)
- 更新サイクルは日次 Cron 起点。即時性は不要 (ADR-006 と整合)

**`userdoc_store.py`**:

- Modal Volume 上の USER.md / MEMORY.md の読み書きと世代スナップショット管理を担うドメイン専用クラス (ADR-015)
- `bootstrap_if_missing(template_dir)`: 初回起動時に Volume に USER.md / MEMORY.md がなければ `seeds/user_initial.md` / `seeds/memory_initial.md` からコピー (再起動冪等)
- `write_with_snapshot(new_user_md, new_memory_md)`: 変更があれば `state/snapshots/USER.md.<UTC>.md` に旧版を退避してから上書き。変更なし (byte-equal) なら None を返す。スナップショットは最大 30 世代保持
- Modal Volume `/root/.brief/` に `USER.md` / `MEMORY.md` / `state/last_digest.json` / `feedback.jsonl` / `state/snapshots/` を格納

**`userdoc_notifier.py`**:

- USER.md / MEMORY.md の更新内容を Slack の専用チャンネルに通知する
- `difflib.unified_diff` で before/after の差分を計算し Block Kit に変換して送信
- change_summary + unified diff hunks + snapshot ファイルパスを 1 メッセージで通知

### 2.8 `seeds/`

- リポジトリで管理される seeds ファイル群。`user_initial.md` と `memory_initial.md` は不変テンプレとしてのみ使用し、本番データは Modal Volume に置く (ADR-015)
- `summarize_prompt.md`: 要約プロンプト初期版。将来 Gemini が改善案を提案する想定 (Sprint 3+)
- `user_initial.md`: USER.md の初期テンプレ (不変)。初回起動時に Volume へコピーされる
- `memory_initial.md`: MEMORY.md の初期テンプレ (不変)。初回起動時に Volume へコピーされる
- `user_md_update_prompt.md`: USER.md / MEMORY.md 更新用プロンプト (ADR-015)

## 3. データフロー (Phase 詳細)

### Phase 1: 前日フィードバック回収

```python
yesterday_message_id = state_store.get_last_message_id()
if yesterday_message_id is None:
    return  # 初回起動時は skip
feedbacks = notifier.collect_feedback(yesterday_message_id)
state_store.append_feedback(feedbacks)  # feedback.jsonl に追記
```

`yesterday_message_id` は前日 Phase 4 完了時に Modal Volume の `state/last_digest.json` に保存する。

### Phase 2: メール取得

```python
emails = gmail_client.fetch_unread(label="Newsletter/Tech", since=timedelta(hours=24))
if not emails:
    notifier.send(blocks=empty_digest_blocks())
    return
```

空の場合も投稿する (silent failure 防止)。

### Phase 3: 要約

```python
prompt = load_seed("summarize_prompt.md")
digest = summarize(emails, prompt=prompt, model="gemini-2.5-flash")
```

### Phase 4: 配信

```python
blocks = formatter.to_block_kit(digest)
posted = notifier.send(blocks)
state_store.set_last_message_id(posted.message_id)
```

### Phase 5: 後処理 + USER.md 更新

```python
gmail_client.mark_processed(emails)
diff = user_md_updater.update_if_ready(feedback_log_path, userdoc_store)
# diff が None なら閾値未満 or 変更なし → スキップ
if diff is not None:
    before_user, before_memory = userdoc_store.read()
    snapshots = userdoc_store.write_with_snapshot(diff.user_md_content, diff.memory_md_content)
    if snapshots is not None:
        snap_user, snap_memory = snapshots
        userdoc_notifier.notify(diff, before_user=before_user, ..., snapshot_user_path=snap_user, ...)
        state_store.rotate_feedback(suffix=f"userdoc-{snap_user.stem}")
```

`user_md_updater.update_if_ready()` は副作用なし (Volume 書き込みは呼び出し側の責務)。Slack 通知成功後のみ `feedback.jsonl` を rotate する。

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

- Sprint 3 で別 Notifier を追加するときに、コード駆動 (境界B) で問題ないか再評価する。

### ADR-005: プロンプトを `seeds/` に分離、コードにベタ書きしない

**決定**: 全プロンプトは `seeds/*.md` に Markdown で書き、実行時に読み込む。

**理由**:

- プロンプトは仕様の一部であり、コード差分よりプロンプト差分のほうがレビューしやすい。
- seeds/ を Markdown で管理する流儀と一貫させる。
- A/B 実験 (プロンプト差し替え) がしやすい。

**強制**: `summarize.py` などにプロンプト相当の長文文字列リテラルが含まれていないかをアーキテクチャテストで検出する (`tests/architecture/test_prompts_in_seeds.py`)。

### ADR-006: HITL を Slack webhook ではなく翌朝 polling

**決定**: Slack のリアクション/ボタン/スレッド返信は、Modal Function 内から翌朝の Phase 1 で polling 取得する。Events API / Socket Mode は使わない。

**理由**:

- Events API (HTTPS webhook) は Modal web endpoint で受けられるが、ボタンクリックを即時処理する要件がない。
- Socket Mode は WebSocket 常駐が必要で、Modal の serverless 文脈と相反する。Hermes Slack Gateway も Socket Mode (`AsyncSocketModeHandler`) 専用であり、同じ制約から Hermes ホストを別途常駐させる必要がある (ADR-011 参照)。
- Polling は構造がシンプルで、Phase 1 として既存の Phase 構造に自然に乗る。
- 即時性が要らない (フィードバックは翌朝の生成で活きればよい) ため、polling のレイテンシは無問題。

### ADR-007: メール処理状態を Gmail ラベルで管理

**決定**: 処理済みメールは `Newsletter/Tech/Processed` ラベルで識別する。別途 DB は持たない。

**理由**:

- 状態管理を Gmail に寄せると、Modal Volume に状態を持たない/減らせる。
- 何が処理済みかを Gmail UI から直接確認・修正できる (デバッグ性)。
- ラベル付与は Gmail API で 1 コール。

### ADR-008: スケジュールは Modal Cron が唯一の起点

**決定**: 毎日 06:30 JST 起動は Modal の `modal.Cron` で行う。外部エージェントや別プロセスの cron は使わない。

**理由**:

- 常駐プロセスの cron は Modal の hibernate/wake モデルと相反する。
- 二重スケジューラは混乱の元。
- Modal Cron は宣言的で、コードを読めばスケジュールが自明。

### ADR-009: Gmail OAuth スコープは gmail.modify

**決定**: Gmail API に要求するスコープは `https://www.googleapis.com/auth/gmail.modify` のみ。

**理由**:

- `mark_processed` (`Newsletter/Tech/Processed` ラベル付与, ADR-007) にはラベル変更権限が必要。`gmail.readonly` では `users.messages.modify` API が呼べない。
- `gmail.send` はこのサービスの責務外 (CLAUDE.md「送信に Gmail を使わない」)。
- フルアクセス (`https://mail.google.com/`) は最小権限原則に反する。

**影響**: OAuth 認可画面に「メールの読み取り、構成、削除、送信」と表示されるが (Google 側の固定表記)、実際に送信は行わない。利用者への説明は `docs/setup.md` (T1.13) で補足する。

### ADR-010: オブザーバビリティバックエンドを Logfire に統一する

**ステータス**: *改定済み (初版は LangSmith + Logfire 二段構成だったが廃止)*

**決定**: LLM 入出力の追跡および処理フロー (Phase 1-5) の可視化を Logfire (OTel ベース) 1 本に統合する。LangSmith は廃止する。

**理由**:

- PydanticAI 導入 (ADR-013) により `logfire.instrument_pydantic_ai()` 1 行で全 LLM スパンが Logfire に自動で乗るようになり、LangSmith の役割が不要になった。
- Logfire は Pydantic 製で OTel 標準に準拠。本プロジェクトの Pydantic v2 との親和性が高く、Modal の short-lived 関数にも `force_flush()` 1 呼び出しで対応できる。
- UI が 1 つになり「LangSmith と Logfire を使い分ける」トレードオフが解消される。

**実装境界**: `logfire` の import は `src/digest/observability.py` 1 ファイルに集約し、他モジュールは薄いラッパ (`span`, `flush`) 経由で使う。アーキテクチャテスト (`test_observability_imports.py`) で強制する。

**フォールバック**: クレデンシャル (`LOGFIRE_TOKEN`) 未設定時は no-op。ローカル `just test` / `just dry-run` への影響なし。

**トレードオフ**: LangSmith 固有の UI (プロンプト diff の並列比較、入出力 playground) は使えなくなる。LLM 品質の専用 UI が必要になったら Logfire 1 本から再検討する。

### ADR-011: Hermes は別ホスト常駐 / morning-brief とは Slack ハブ経由で疎結合 (Superseded)

**ステータス**: *Superseded by ADR-012*

**決定**: Hermes は morning-brief とは別の常駐ホスト (Oracle Cloud Always Free / fly.io / VPS 等) に置き、Slack の専用チャネルを中継ハブとして通信する。

- `#brief-to-hermes`: morning-brief → Hermes (日次フィードバック中継、Sprint 2)
- `#hermes-to-brief`: Hermes → morning-brief (プロンプト改善案中継、Sprint 3+ 想定)

**背景**: Hermes Slack Gateway の実装 (`nousresearch/hermes-agent` 内 `gateway/platforms/slack.py`) は Socket Mode (`AsyncSocketModeHandler`) 専用で、WebSocket 常駐が必須。Modal serverless では動かせないことが判明した。当初は「Hermes を Modal で動かす / Modal Sandbox で起動する」案を検討したが、いずれも Socket Mode の常駐要件と相反する。

**選択肢**:

- A. **Slack ハブ経由 (採用)**: 両者 Slack のクライアントとして振る舞い、直接通信は持たない
- B. Hermes 側に Web Endpoint を立てて morning-brief から HTTP で叩く: 認証管理が増える / 接続点が増える
- C. 共有ストレージ (S3 等) 経由: 両者がストレージに依存し Slack 中心の運用と乖離

**決定理由**: 案A は両者が完全に疎結合になり、片方がダウンしても他方は動く。Slack を Sprint 1 で既に使っているので新たな外部依存追加なし。デバッグも Slack UI で目視できる。

**トレードオフ**:

- Sprint 2 では Hermes ホスト構築まで踏み込まない (受け手不在で `#brief-to-hermes` への投函のみ動作確認する)
- Slack 無料 plan の保持期間 (90 日) を超えると古い投函が消える。Hermes 立ち上げ後は直近 90 日分を初回読み込みで消費する前提で観察ログ (T2.5) を始める
- Hermes 自身の永続状態 (USER.md / MEMORY.md / skills) は Hermes ホスト側にあり morning-brief からは直接観察できない。観察手段は Hermes ホスト側のファイル直視か、Hermes が `#hermes-to-brief` に発信するスナップショットに依存する

### ADR-012: Hermes を廃止し境界B (コード駆動 + LLM サブルーチン) を採用

**ステータス**: *Supersedes ADR-011*

**決定**: Hermes Agent を完全廃止し、Python コードがオーケストレーションを担う「境界B」構成に移行する。Gemini は「要約」と「USER.md / MEMORY.md 更新差分の生成」の 2 サブルーチンとして呼ぶ。これに伴い Slack interactivity webhook は使わず、`[ミュート]` ボタン (`ButtonFeedback`) は廃止し、ミュート意思は 🔇 リアクションで表明する。

**背景**:

- Hermes は当初「秘書として Gmail 取得・Slack 投稿・要約まで自律的に行う」想定だった。しかし実装を進めると、これらすべてを Python コードが担当し、Hermes は「USER.md を持つ DB + 自律更新エンジン」にとどまっていた。秘書がやるべき仕事を Python が代行しているなら、agent framework を使う本来の意義が薄い。
- さらに Hermes Slack Gateway は Socket Mode 専用で Modal serverless と相反する (ADR-011 の本来の壁)。これを解消するためだけに別ホスト常駐構成 (ADR-011) を採用していたが、インフラ管理コストが発生する。

**選択肢**:

- A. **境界A (agent 駆動)**: Hermes や Claude Agent SDK に Gmail / Slack / Gemini をツールとして渡し、agent loop がオーケストレーションを担う。「秘書が自分でやる」に最も近いが、Modal serverless と socket 常駐の整合問題が残る
- B. **境界B (コード駆動 + LLM サブルーチン)**: 現構成のまま Hermes を廃止し、USER.md 更新だけ Gemini に任せる。ambient agent の学習目的は「feedback → USER.md 自動更新ループ」で達成する ← **採用**

**理由**:

- ループの主役は「Gmail 取得 → 要約 → Slack 投稿 → feedback 収集 → USER.md 更新」の日次サイクル。これはステートマシンより Pipeline (コード駆動) が素直で、テスト・デバッグが容易。
- Gemini の LLM 判断が必要なのは「要約の内容」と「feedback 解釈 → USER.md diff 生成」の 2 点だけ。それ以外は確定的な処理なので LLM に委ねる必要がない。
- インフラを Modal 1 本に集約できる。

**トレードオフ**:

- ambient agent の「自律的な学習エージェント」としての汎用性は下がる。ただし USER.md の自動更新ループは維持されており、学習目的 (§1.2) は達成できる。
- 将来「Gemini に tool を渡して自律させたい」となった場合は、既存の `gmail_client.py` / `slack.py` 等をツールとして再利用できる。境界A への移行コストは相対的に小さい。

### ADR-013: LLM 呼び出しを PydanticAI 経由に統一する

**決定**: すべての LLM 呼び出しを PydanticAI 経由で行う。現状の `google-genai` 直叩きは PydanticAI に置き換える (T2.3 で実装)。

**理由**:

- **retry 内蔵**: validation 失敗時に LLM へ「直して」と自動再試行 (max_retries 設定可)。日次バッチで JSON が壊れると翌日まで復旧されないため、再試行の組み込みは実用上重要。
- **プロバイダ抽象**: Gemini ↔ Claude ↔ OpenAI をモデル文字列 1 つで切り替えられる。LLM 比較やコスト最適化が容易になる。
- **Logfire ネイティブ統合**: `logfire.instrument_pydantic_ai()` 1 行で全 LLM スパンが自動で Logfire に乗る (ADR-010 との相乗効果)。

**コスト評価**: ライブラリは OSS で無料。API トークン消費は retry が発動しない限り誤差レベル (月数十円増の見込み)。

**トレードオフ**:

- 依存が 1 つ増える (`pydantic-ai`)。
- google-genai 固有の機能 (例: video input、thinking mode の細かい設定) を PydanticAI 越しに使いにくい場合がある。

### ADR-014: USER.md / MEMORY.md をリポジトリで Git 管理する

**ステータス**: *Superseded by ADR-015*

**決定**: USER.md / MEMORY.md は `seeds/` 配下にコミットし Git で履歴管理する。Gemini が diff を生成 → GitHub PR 化 → 人間マージ → Modal 自動デプロイのループで更新する (T2.4 / T2.5 で実装)。

**理由**:

- **Git log で学習の証跡を追跡できる**: `git diff` / `git log seeds/USER.md` で「いつ・どんな好みが追加されたか」を直接確認できる。Hermes ホスト側のファイルは morning-brief から見えず観察が難しかった (ADR-011 のトレードオフを解消)。
- **ロールバック可能**: 誤った更新は `git revert` で戻せる。
- **Modal Volume に USER.md を置く必要がなくなる**: Volume には `state/last_digest.json` と `feedback.jsonl` のみ。永続化の責務が明確になる。
- **インフラが Modal 1 本に集約**: Hermes ホスト不要。

**承認モデル**: Gemini diff 提案 → GitHub PR → 人間マージ。人間マージで承認を表明するため自律性は維持しつつ、意図しない更新をロールバックできる。信頼が積み上がれば自動マージに移行する想定。

**トレードオフ**:

- リポジトリに個人の嗜好情報 (USER.md) が含まれる。プライベートリポジトリでの運用が前提。
- PR マージ → Modal 自動デプロイのサイクルが必要 (GitHub Actions or gh CLI から Modal deploy を呼ぶ)。設計詳細は T2.5 で詰める。

### ADR-015: USER.md / MEMORY.md を Modal Volume で管理し GitHub PR フローを廃止する

**ステータス**: *Supersedes ADR-014*

**決定**: USER.md / MEMORY.md は Modal Volume (`/root/.brief/`) 上で直接管理する。Gemini が生成した diff を Volume に上書き保存し、変更内容 (change_summary + before/after unified diff) を Slack の専用チャンネルに通知する。GitHub PR フロー (ADR-014) は廃止する。

**背景**: `bellwood4486/morning-brief` は public リポジトリとして公開しており、個人の嗜好情報 (USER.md) を Git 履歴に含めることはプライバシー上許容できない。ADR-014 の「プライベートリポジトリでの運用が前提」というトレードオフが、実際の運用 (public OSS) と矛盾していた点が T2.5 着手時に顕在化した。

**更新フロー**:

1. Phase 5 で `user_md_updater.update_if_ready()` が `UserMdDiff` を生成 (副作用なし)
2. `userdoc_store.write_with_snapshot()` が Volume の USER.md / MEMORY.md を上書きし、旧版を `state/snapshots/USER.md.<UTC>.md` に退避
3. `userdoc_notifier.notify()` が change_summary + unified diff + snapshot パスを Slack 専用チャンネルに投稿
4. 両方成功後、`state_store.rotate_feedback()` で `feedback.jsonl` を archived 名にリネーム

**ロールバック**: Volume 内スナップショット (最大 30 世代、超過分を古い順に prune) + Slack 投稿テキストの両建て。

**理由**:

- **プライバシー**: 個人の嗜好情報が public Git 履歴に出ない。
- **シンプル**: gh CLI / GitHub Actions / Modal deploy の連鎖が不要になる。Volume への `os.replace` で完結する。
- **Slack 通知がバックアップを兼ねる**: unified diff が Slack に残るため、Volume が壊れても Slack テキストから復元可能。
- **冪等性**: bootstrap は「Volume に無いとき」だけ動く。スナップショットの同等性チェック (`write_with_snapshot` → None) で二重通知を防ぐ。

**トレードオフ**:

- `git log seeds/USER.md` で学習の証跡を追えなくなる。Logfire の `phase5.write_userdoc` span と Slack 投稿で代替する。
- `seeds/USER.md` / `seeds/MEMORY.md` はリポジトリから削除。`user_initial.md` / `memory_initial.md` だけが不変テンプレとしてリポジトリに残る。

### ADR-016: Slack チャンネルを 2 本に集約し operations channel を導入する

**ステータス**: *Adopted*

**決定**: 従来の `digest_channel` / `alerts_channel` / `userdoc_channel` の 3 本構成を `digest_channel` / `operations_channel` の 2 本に集約する。`alerts_channel` を廃止し、エラー通知・実行サマリ・USER.md 更新通知をすべて `operations_channel` に集約する。毎日 1 実行 = 1 サマリメッセージを終了時に必ず投稿し、「動いているか」を一目で確認できるようにする。

**背景**: 3 チャンネル構成では「今日動いたか」を確認するために digest / alerts / userdoc の 3 箇所を横断する必要があった。また、Phase 1/2 のエラーは当時どの Slack チャンネルにも通知されず黙って死ぬ問題があった。さらに `#newsletter-digest` に「本日は対象メールなし」が混ざりダイジェストフィードとして見づらかった。

**実行サマリの仕様**: `src/digest/operations_notifier.py` の `OperationsRunSummaryNotifier` が担当。`RunSummary(status: ok|empty|error, digest_count, digest_message_id, userdoc_updated, errors: list[PhaseError])` を `digest_job` の finally ブロックで必ず投稿する。dry_run=True 時は stdout に出力して Slack には投稿しない。

**トレードオフ**:

- 正常系 (digest あり) の日は `#newsletter-digest` と `#operations` の両方に投稿が入る (digest が届いた事実は operations でも確認可能)。
- Modal Function タイムアウト (`timeout=600`) や SIGKILL の場合は Python の `finally` が走らず operations 通知も飛ばない。この境界では Modal ダッシュボード側の死活監視に依存する。
- Modal/Logfire 実行ページへの URL リンクは後続対応。`RunSummary.digest_message_id` フィールドを保持しており、後から拡張しやすい。

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
| Phase 1 失敗 (フィードバック取得) | warning ログ + `#operations` サマリの errors に記録。Phase 2 以降は継続 (今日のダイジェストは届く)。 |
| Phase 2 が空 (対象メールなし) | `#newsletter-digest` には何も投稿しない。`#operations` に「対象メールなし」のサマリを投稿。Phase 5 はスキップ。 |
| Phase 2 失敗 (Gmail エラー) | `#operations` サマリの errors に記録して早期終了。Phase 5 はスキップ。 |
| Phase 3 失敗 (Gemini エラー) | `#operations` サマリに error ステータスと詳細を投稿。再実行は手動。 |
| Phase 4 失敗 (Slack 送信エラー) | `#operations` サマリに error ステータスを投稿。Gemini 出力は Modal の stdout にログとして残す。 |
| Phase 5 Volume 書き込み失敗 | `#operations` サマリの errors に記録 (status は ok のまま)。feedback.jsonl は rotate しない (翌日の同等性チェックで skip)。 |
| Phase 5 Slack 通知失敗 | Volume は更新済み。`#operations` サマリの errors に記録。feedback.jsonl は rotate しない。翌日の `write_with_snapshot` が同等性チェックで None を返し二重通知を防ぐ。 |
| Modal Function タイムアウト (600s) / SIGKILL | Python の `finally` が走らないため `#operations` 通知も飛ばない。Modal ダッシュボード側の死活監視に依存する。 |
| Modal Function 自体が起動しない | 検知不可 (Modal の死活監視に依存)。割り切り。 |

`#operations` channel への通知も Slack なので、Slack 自体が落ちると気付けない。これは許容する (NG: 厳密な SLA)。

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
