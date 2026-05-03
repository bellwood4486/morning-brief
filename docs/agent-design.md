# LLM サブルーチンと seeds 運用方針

## 1. このドキュメントの位置付け

`docs/design.md` がアーキテクチャ判断 (ADR) を記録するのに対し、本ドキュメントは **LLM サブルーチンの運用方針と seeds ファイルの育て方** を記録する。

- 読者: このリポジトリのオーナー (= 自分)。Gemini にどう関与させるか・seeds をどう育てるかを知りたいとき。
- `docs/design.md` に書いた内容とは重複しない。判断の背景は `docs/design.md` を参照のこと。

## 2. 設計方針の前提

morning-brief は **ambient agent** としての学習目的で設計されている ([要件](requirements.md) §1.2)。Hermes Agent を廃止し (ADR-012)、以下の方針を採用する。

- **オーケストレーション**: Python コードが Phase 1-5 を順に実行する。
- **LLM の役割**: 要約 (Phase 3) と USER.md 更新差分の生成 (Phase 5) の 2 サブルーチン。
- **スケジュール起点**: `modal.Cron` のみ。常駐プロセスは持たない ([ADR-008](design.md#adr-008))。
- **永続状態**: Modal Volume には `state/last_digest.json` と `feedback.jsonl` のみ。USER.md / MEMORY.md はリポジトリで Git 管理 (ADR-014)。

## 3. 永続状態の構造

```text
Modal Volume: /root/.brief/
├── state/
│   └── last_digest.json  # 前日のダイジェストの Slack message_id
└── feedback.jsonl         # 蓄積フィードバック (JSONL 形式、Phase 1 で追記)
```

```text
リポジトリ: seeds/
├── USER.md          # ユーザープロファイル (Gemini diff 提案 → 人間マージで更新)
├── MEMORY.md        # 長期記憶 (同上)
├── summarize_prompt.md  # 要約プロンプト初期版
└── user_initial.md      # USER.md を初めて作る際の記入テンプレ (不変)
```

morning-brief は seeds/ 内のファイルをリードオンリーで参照し、Gemini が差分を生成 → GitHub PR → 人間マージ → Modal 自動デプロイのループで更新する。

## 4. seeds ファイルの方針

| ファイル | 初期記入 | Sprint 2 以降 |
|---|---|---|
| `user_initial.md` | ユーザーが手書きで埋める (テンプレ) | 不変。初回セットアップで USER.md の叩き台として使う |
| `USER.md` | `user_initial.md` を元にユーザーが初期作成 | Gemini が feedback を解釈して diff 提案 → 人間マージで育つ |
| `MEMORY.md` | 初期は空 (または最小記述) | 同上 |
| `summarize_prompt.md` | ユーザーが初期版を記入 | Sprint 3+ で Gemini が改善案を提案予定。Sprint 2 は人手で修正 |

プロンプトをコードにハードコードしてはいけない。全プロンプトは `seeds/*.md` から読み込む ([CLAUDE.md](../CLAUDE.md) 「やってはいけないこと §4」、`tests/architecture/test_prompts_in_seeds.py` で強制)。

### 4.1 `seeds/user_initial.md`

USER.md を初めて作る際の記入テンプレ。5 つのセクション (興味分野 / 嫌うトピック / 読み方の癖 / ミュート済み送信元 / 英語レベル) をユーザーが手書きで埋め、`seeds/USER.md` の初期コミットとして使う。

- **Sprint 1 〜 の前提**: セットアップ時に `USER.md` を作成して commit しておくこと ([docs/setup.md](setup.md) §5 参照)。
- `user_initial.md` 自体はテンプレとして不変。

### 4.2 `seeds/USER.md` と `seeds/MEMORY.md`

Gemini が feedback.jsonl を解釈して差分を生成するターゲットファイル。

- **更新サイクル**: Phase 5 の `user_md_updater.update_if_ready()` が蓄積フィードバック量を判断し、一定量に達したら Gemini (PydanticAI 経由) に diff を生成させる
- **承認モデル**: 生成した diff は GitHub PR として作成される。ユーザーがレビュー・マージした時点で確定する。誤った変更は `git revert` で戻せる
- **ミュート意思の反映**: 🔇 リアクションはフィードバックとして収集され、Gemini が「どの送信元をミュートすべきか」を推論して USER.md に反映する。morning-brief 側はリアクションを単に記録するだけで解釈は Gemini 任せ

### 4.3 `seeds/summarize_prompt.md`

要約プロンプトの初期版。ユーザーが以下の箇所を必ず記入してから本番稼働させること。

- **役割説明のトーン調整**: 要約の文体や技術的深さの好みを書く
- **TL;DR 選定基準**: 優先したいトピック・除外したいカテゴリを書く。ここが空だと Gemini の判断に完全に委ねられる

Sprint 2 では人間が記入した初期版のまま動かす。Sprint 3+ で USER.md / MEMORY.md の蓄積を踏まえた改善案を Gemini が提案する想定 (Push 型)。

## 5. LLM サブルーチンのインターフェース (Sprint 2 実装予定)

### `src/digest/state_store.py`

| メソッド | 責務 |
|---|---|
| `get_last_message_id() -> str \| None` | 前日ダイジェストの Slack `ts` を読む。ファイル不在時は `None` |
| `set_last_message_id(message_id: str)` | 原子的書き込み (一時ファイル + `os.replace`) |
| `append_feedback(feedbacks: list[Feedback])` | feedback.jsonl に追記 (JSONL 形式) |

### `src/digest/user_md_updater.py`

| メソッド / 関数 | 責務 |
|---|---|
| `update_if_ready(feedback_log_path, repo_root)` | feedback.jsonl の件数が閾値を超えたら Gemini に USER.md diff を生成させ GitHub PR を作成する。閾値未満なら no-op |

`update_if_ready` の内部:

1. `feedback.jsonl` を読んで ReactionFeedback / ThreadReplyFeedback を構造化
2. `seeds/USER.md` / `seeds/MEMORY.md` を読み込む
3. PydanticAI (Gemini 経由) に「この feedback を踏まえた USER.md / MEMORY.md の差分を生成せよ」と依頼 → `UserMdDiff` 型 (pydantic モデル) として受け取る
4. diff を seeds/ に書き込み、`gh pr create` で PR を作成 (T2.5 で詳細設計)

## 6. フィードバック反映ルール

### 6.1 入力 (Slack 上のフィードバック)

ユーザーは翌朝の `digest_job` 実行までの間に以下の操作でフィードバックを残す。

- **リアクション**: 👍 (良かった) / 👎 (微妙) / 🔥 (超良かった) / 🔇 (ミュート希望)
- **スレッド返信**: 自由記述コメント

これらは `SlackNotifier.collect_feedback()` で `Feedback` 型 (`ReactionFeedback | ThreadReplyFeedback`) のリストに変換され、`state_store.append_feedback()` で feedback.jsonl に書き込まれる。

### 6.2 反映先

| フィードバック | 反映経路 |
|---|---|
| リアクション (👍/👎/🔥/🔇) | feedback.jsonl に記録 → Gemini が USER.md diff を生成 → PR マージで反映 |
| スレッド返信 | 同上 (自然言語のまま記録。Gemini 側が LLM で意味を解釈) |

morning-brief 側は解釈・判断をしない (Gemini に委ねる)。

### 6.3 反映タイミング

- **Phase 1**: `collect_feedback()` で取得したフィードバックを `state_store.append_feedback()` で記録。
- **Phase 5**: `user_md_updater.update_if_ready()` で蓄積量を判断し、閾値到達時に Gemini に diff 生成を依頼。

### 6.4 反映が "効いている" ことの確認

- `git log seeds/USER.md` で更新履歴を確認
- `git diff <old>..<new> -- seeds/USER.md` で何が変わったか確認
- Logfire ダッシュボードで `user_md_updater` のスパンを確認

## 7. 観察方法

### Sprint 2 段階の観察手段

- `modal_app.py` の stdout ログ (Logfire trace) で Phase 実行を確認
- `git log --oneline seeds/USER.md` で USER.md の更新履歴を確認
- feedback.jsonl の件数推移で「どれだけフィードバックが溜まっているか」を目視

### Sprint 3+ で整備予定

- `scripts/weekly_report.py`: USER.md 差分 / フィードバック統計 / コストを毎週 Slack に自動投稿 ([requirements.md](requirements.md) NFR-6)

## 8. 関連ドキュメント

| ドキュメント | 用途 |
|---|---|
| [`docs/design.md`](design.md) | アーキテクチャ判断 (ADR-012/013/014) |
| [`docs/requirements.md`](requirements.md) | 機能要件 (FR-4/FR-5) と非機能要件 (NFR-6) |
| [`docs/setup.md`](setup.md) | 初回セットアップ手順 |
| [`seeds/user_initial.md`](../seeds/user_initial.md) | ユーザープロファイルの初期テンプレ |
| [`seeds/summarize_prompt.md`](../seeds/summarize_prompt.md) | 要約プロンプト |
| [`CLAUDE.md`](../CLAUDE.md) | 運用ガードレール (やってはいけないこと) |
