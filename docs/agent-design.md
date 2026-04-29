# Hermes Agent Design

## 1. このドキュメントの位置付け

`docs/design.md` がアーキテクチャ判断 (ADR) を記録するのに対し、本ドキュメントは **Hermes と seed ファイルの運用方針** を記録する。

- 読者: このリポジトリのオーナー (= 自分)。Hermes をどう育てるか・触るかを知りたいとき。
- `docs/design.md` に書いた内容とは重複しない。判断の背景は `docs/design.md` を参照のこと。

## 2. Hermes 採用の前提

morning-brief は **ambient agent** としての学習目的で設計されている ([要件](requirements.md) §1.2)。Hermes はそのフィードバックループを担う LLM エージェントフレームワークで、ユーザープロファイルや学習済みスキルを Modal Volume に永続化する。

- **スケジュール起点**: `modal.Cron` のみ。Hermes 独自の cron 機能は使わない ([ADR-008](design.md#adr-008-スケジュールは-modal-cron-起点))。
- **永続化基盤**: Modal Volume `/root/.hermes/`。コード内からは `HermesBridge` 経由でのみアクセスする ([ADR-007](design.md#adr-007-メール処理状態は-gmail-ラベルで管理))。

## 3. 永続状態の構造 (`~/.hermes/`)

Modal Volume に以下のファイルを保持する。

```text
~/.hermes/
├── USER.md          # ユーザープロファイル (seeds/user_initial.md から初期化)
├── MEMORY.md        # Hermes が蓄積する長期記憶
├── skills.db        # 学習済みスキルのデータベース
└── state/
    └── last_digest.json  # 前日のダイジェストの Slack message_id
```

`USER.md` / `MEMORY.md` / `skills.db` は Hermes が管理する。本体コードが直接読み書きするのは `state/last_digest.json` のみで、`HermesBridge` 経由でアクセスする。

**直接 Volume を書き換えてはいけない** ([CLAUDE.md](../CLAUDE.md) 「やってはいけないこと §3」)。

## 4. seed ファイルの方針

`seeds/` 配下 3 ファイルの位置付けを「初期は人が書く / Hermes が育てる」で整理する。

| ファイル | 初期記入 | Sprint 2 以降 |
|---|---|---|
| `user_initial.md` | ユーザーが手書きで埋める | Hermes は `USER.md` ランタイムコピーを更新。`user_initial.md` 自体は不変 |
| `summarize_prompt.md` | ユーザーが初期版を記入 | Hermes は `MEMORY.md` で補正する方針。seed 自体の直接書き換えは Sprint 2 で設計 |
| `newsletter_digest.md` | 叩き台のみ人が書く | `TODO (Hermes が育てる領域)` セクションを Hermes が自動更新。人は触らない |

プロンプトをコードにハードコードしてはいけない。全プロンプトは `seeds/*.md` から読み込む ([CLAUDE.md](../CLAUDE.md) 「やってはいけないこと §4」、`tests/architecture/test_prompts_in_seeds.py` で強制)。

### 4.1 `seeds/user_initial.md`

ユーザープロファイルの初期テンプレ。5 つの `<!-- TODO -->` セクション (興味分野 / 嫌うトピック / 読み方の癖 / ミュート済み送信元 / 英語レベル) はすべてユーザーが手書きで埋める。

- **Sprint 1 の必須前提**: セットアップ時に記入を済ませること ([docs/setup.md](setup.md) §5 参照)。
- **Sprint 2 以降**: Hermes は `~/.hermes/USER.md` (ランタイムコピー) を更新する。`seeds/user_initial.md` は初期値として固定し、Volume を再作成したとき以外は変更しない。
- **ミュート済み送信元** セクションだけは Hermes が `[ミュート]` ボタン押下を学習した際に自動追記する想定 (Sprint 2 / T2.2 で実装)。

### 4.2 `seeds/summarize_prompt.md`

要約プロンプトの初期版。ユーザーが以下の箇所を必ず記入してから本番稼働させること。

- **役割説明のトーン調整** (L3-4 の `<!-- TODO -->`): 要約の文体や技術的深さの好みを書く。
- **TL;DR 選定基準** (L42-43 の `<!-- TODO -->`): 優先したいトピック・除外したいカテゴリを書く。ここが空だと Gemini の判断に完全に委ねられる。

Sprint 2 以降の方針は未確定。フィードバックループが動いた後、Hermes は `seeds/summarize_prompt.md` を直接書き換えるか `MEMORY.md` 側で補正するかを T2.2 で設計する。

### 4.3 `seeds/newsletter_digest.md`

[agentskills.io](https://agentskills.io) 形式のスキル定義ファイル。`name` / `description` / `when_to_use` / `概要` / `参照` セクションは人が書いた初期版。

**`## TODO (Hermes が育てる領域)` セクションは Hermes が自動更新する想定で、人は触らない。**

- `改善方針` / `成功例` / `失敗例` は Sprint 2 以降のフィードバックループで埋まる。

## 5. Hermes と本体コードの境界 (HermesBridge)

`src/digest/hermes_bridge.py` の `HermesBridge` が Modal Volume との唯一の接点。`modal_app.py` からのみ使う。

### Sprint 1 で実装済みの API

| メソッド | 責務 |
|---|---|
| `get_last_message_id() -> str \| None` | 前日ダイジェストの Slack `ts` を読む。ファイル不在時は `None` |
| `set_last_message_id(message_id: str)` | 原子的書き込み (一時ファイル + `os.replace`)。`Path.write_text` 直接書き込みを避けている理由: クラッシュ時に空ファイル / 途中切れ JSON が残り、翌朝 Phase 1 が `JSONDecodeError` で詰まるのを防ぐため |

### Sprint 2 で本実装する API

| メソッド | 現状 | Sprint 2 タスク |
|---|---|---|
| `inject_feedback(feedbacks)` | スタブ (ログのみ) | T2.2 |
| `observe_session(session_log)` | スタブ (ログのみ) | T2.3 |

## 6. フィードバック反映ルール [Sprint 2 で詳細化]

> **Sprint 2 / T2.1-T2.3 で詳細化する。** このセクションは目次として置いている。

### 6.1 入力 (Slack 上のフィードバック)

ユーザーは翌朝の `digest_job` 実行までの間に以下の操作でフィードバックを残す。

- **リアクション**: 👍 (良かった) / 👎 (微妙) / 🔥 (超良かった)
- **ボタン**: `[ミュート]` で送信元をミュート
- **スレッド返信**: 自由記述コメント

これらは `SlackNotifier.collect_feedback()` で `Feedback` 型のリスト ([`src/digest/models.py`](../src/digest/models.py)) に変換され、`HermesBridge.inject_feedback()` に渡される。

### 6.2 反映先 (Sprint 2 で実装)

| フィードバック | 反映先 (予定) |
|---|---|
| リアクション (👍/👎/🔥) | `USER.md` のトピック好み更新、スキル評価スコア |
| `[ミュート]` ボタン | `USER.md` のミュート送信元追記、`config.yaml` のブラックリスト更新 |
| スレッド返信 | `MEMORY.md` への長期記憶追記 |

詳細は [requirements.md](requirements.md) FR-4/FR-5 を参照。

### 6.3 反映タイミング (Sprint 2 で実装)

- Phase 1: `inject_feedback()` でフィードバックを Hermes に渡す。
- Phase 5: `observe_session()` でセッションログを Hermes に渡してスキル自動生成をトリガする。

### 6.4 反映が"効いている"ことの確認

→ §7 参照。

## 7. 観察 / 学習の観察方法 [Sprint 2 で詳細化]

Sprint 2 で以下を導入予定 ([requirements.md](requirements.md) NFR-6)。

- `docs/observation.md`: 学習観察ログの蓄積。`~/.hermes/USER.md` の差分や学習の証跡を手動で記録。
- `scripts/weekly_report.py`: `USER.md` 差分 / スキル数推移 / フィードバック統計 / コストを毎週 Slack に自動投稿。

Sprint 1 段階では `modal_app.py` の stdout ログと `~/.hermes/state/last_digest.json` の内容確認で動作を確認する。

## 8. 関連ドキュメント

| ドキュメント | 用途 |
|---|---|
| [`docs/design.md`](design.md) | アーキテクチャ判断 (ADR)。Hermes 採用/Modal 採用の根拠 |
| [`docs/requirements.md`](requirements.md) | 機能要件 (FR-4/FR-5) と非機能要件 (NFR-6) |
| [`docs/setup.md`](setup.md) | 初回セットアップ手順 |
| [`seeds/user_initial.md`](../seeds/user_initial.md) | ユーザープロファイルの初期テンプレ |
| [`seeds/summarize_prompt.md`](../seeds/summarize_prompt.md) | 要約プロンプト |
| [`seeds/newsletter_digest.md`](../seeds/newsletter_digest.md) | Hermes スキル定義 |
| [`CLAUDE.md`](../CLAUDE.md) | 運用ガードレール (やってはいけないこと) |
