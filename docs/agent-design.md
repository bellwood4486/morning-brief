# Hermes Agent Design

## 1. このドキュメントの位置付け

`docs/design.md` がアーキテクチャ判断 (ADR) を記録するのに対し、本ドキュメントは **Hermes と seed ファイルの運用方針** を記録する。

- 読者: このリポジトリのオーナー (= 自分)。Hermes をどう育てるか・触るかを知りたいとき。
- `docs/design.md` に書いた内容とは重複しない。判断の背景は `docs/design.md` を参照のこと。

## 2. Hermes 採用の前提

morning-brief は **ambient agent** としての学習目的で設計されている ([要件](requirements.md) §1.2)。Hermes はそのフィードバックループを担う LLM エージェントフレームワークで、ユーザープロファイルや学習済みスキルを自身のホスト側に永続化する。

- **スケジュール起点**: `modal.Cron` のみ。Hermes 独自の cron 機能は使わない ([ADR-008](design.md#adr-008-スケジュールは-modal-cron-起点))。
- **Sprint 1**: morning-brief 側の Modal Volume (`/root/.hermes/`) には `state/last_digest.json` のみ保存。`HermesBridge` 経由でのみアクセスする。
- **Sprint 2 以降 (案A / [ADR-011](design.md#adr-011))**: Hermes 自身の永続状態 (USER.md / MEMORY.md / skills) は **Hermes ホスト側** (別ホスト常駐) に存在する。morning-brief からは Slack チャネル `#brief-to-hermes` 経由で間接的にしかやり取りしない。

## 3. 永続状態の構造

案A ([ADR-011](design.md#adr-011)) 採用により、永続状態は **morning-brief 側** と **Hermes ホスト側** に分離する。

### morning-brief 側 (Modal Volume `/root/.hermes/`)

```text
/root/.hermes/
└── state/
    └── last_digest.json  # 前日のダイジェストの Slack message_id
```

`HermesBridge` 経由でのみアクセスする。これ以外のファイルは morning-brief 側の Volume には存在しない。

### Hermes ホスト側 (別環境 / 別ホスト常駐)

```text
~/.hermes/                  # Hermes プロセスの HERMES_HOME
└── memories/
    ├── USER.md             # ユーザープロファイル (seeds/user_initial.md から初期化)
    └── MEMORY.md           # Hermes が蓄積する長期記憶
(skills 等は Hermes 側の管理)
```

morning-brief は Hermes ホスト側のファイルに直接アクセスしない。`#brief-to-hermes` への投函メッセージを受け取った Hermes が、自分で memory tool を使って更新する。

**直接 Hermes 側 Volume を書き換えてはいけない** ([CLAUDE.md](../CLAUDE.md) 「やってはいけないこと §3」)。

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
- **Sprint 2 以降 (案A)**: Hermes は Hermes ホスト側の `~/.hermes/memories/USER.md` を更新する。morning-brief 側からは差分を直接観察できないため、観察手段は Hermes ホストへの SSH または Hermes が `#hermes-to-brief` に発信するスナップショットに依存する (Sprint 3+)。`seeds/user_initial.md` 自体は不変。
- **ミュート意思の伝達**: `[ミュート]` ボタンは廃止済み (Sprint 2 / D-3)。ミュート希望は 🔇 リアクションまたはスレッド返信 (自然言語) で伝え、Hermes 側が推論して USER.md に反映する。

### 4.2 `seeds/summarize_prompt.md`

要約プロンプトの初期版。ユーザーが以下の箇所を必ず記入してから本番稼働させること。

- **役割説明のトーン調整** (L3-4 の `<!-- TODO -->`): 要約の文体や技術的深さの好みを書く。
- **TL;DR 選定基準** (L42-43 の `<!-- TODO -->`): 優先したいトピック・除外したいカテゴリを書く。ここが空だと Gemini の判断に完全に委ねられる。

Sprint 2 では `summarize_prompt.md` は人間が記入した初期版のままで動かす。Sprint 3+ 想定のプロンプト改善ループ (Push 型):

1. Hermes が一定周期で USER.md / MEMORY.md を踏まえて改善案を生成
2. `#hermes-to-brief` に新プロンプト全文を投函
3. morning-brief が次回 Cron 起動時にチャンネルを polling して取り込み
4. Modal Volume 内の seed を上書き → Phase 3 で新プロンプトで要約

承認モデルは当面手動 (ユーザーが ✅ リアクションした案だけ採用)。信頼が積み上がったら自動採用に移行する想定。

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

### Sprint 2 で本実装 / 追加する API

| メソッド | 状態 | 説明 |
|---|---|---|
| `inject_feedback(feedbacks)` | **Sprint 2 で本実装** (T2.2) | `Notifier` (DI) 経由で `#brief-to-hermes` に mrkdwn サマリ + JSON ペイロードを投函。空 feedbacks でも生存シグナルとして 1 通送る |
| `observe_session(session_log)` | Sprint 2 はスタブ据え置き (T2.3 で本実装) | Phase 5 での呼び出し位置のみ Sprint 2 で追加 |

## 6. フィードバック反映ルール

### 6.1 入力 (Slack 上のフィードバック)

ユーザーは翌朝の `digest_job` 実行までの間に以下の操作でフィードバックを残す。

- **リアクション**: 👍 (良かった) / 👎 (微妙) / 🔥 (超良かった) / 🔇 (ミュート希望)
- **スレッド返信**: 自由記述コメント (規約なし。自然言語で Hermes が推論)

`ButtonFeedback` は廃止済み (Sprint 2 / D-3)。interactivity webhook を使わない案A 方針と整合する。

これらは `SlackNotifier.collect_feedback()` で `Feedback` 型のリスト ([`src/digest/models.py`](../src/digest/models.py)) に変換され、`HermesBridge.inject_feedback()` に渡される。

### 6.2 反映先 (案A / ADR-011)

| フィードバック | 反映経路 |
|---|---|
| リアクション (👍/👎/🔥/🔇) | `#brief-to-hermes` 経由で Hermes に渡される。Hermes が memory tool で `USER.md` / `MEMORY.md` を自律更新 |
| スレッド返信 | 同上 (自然言語のまま渡す。Hermes 側が LLM で意味を解釈する) |

morning-brief 側は反映先の判断をしない (Hermes に委ねる)。`config.yaml` のブラックリスト更新も行わない (Hermes 側で管理)。

詳細は [requirements.md](requirements.md) FR-4/FR-5 を参照。

### 6.3 反映タイミング

- **Phase 1**: `inject_feedback()` でフィードバックを `#brief-to-hermes` に投函。fire-and-forget (Hermes の応答は待たない)。
- **Phase 5**: `observe_session()` でセッションログを Hermes に渡してスキル自動生成をトリガする (Sprint 2 はスタブ、T2.3 で本実装)。

### 6.4 反映が"効いている"ことの確認

→ §7 参照。

## 7. 観察 / 学習の観察方法

案A ([ADR-011](design.md#adr-011)) では Hermes の永続状態が別ホストにあるため、観察手段が Sprint ごとに段階的に整備される。

### Sprint 2 段階の観察手段

- `modal_app.py` の stdout ログ (LangSmith / Logfire trace) で Phase 実行を確認
- `#brief-to-hermes` の投函メッセージを Slack 上で目視し、どんなフィードバックが Hermes に渡ったか確認
- `~/.hermes/state/last_digest.json` の内容確認で Phase 4 完了を確認

### Sprint 3+ で整備予定 (T2.3-T2.5)

- `docs/observation.md`: 学習観察ログの蓄積。Hermes 側の `USER.md` 差分や学習の証跡を手動で記録。
- `scripts/weekly_report.py`: `USER.md` 差分 / フィードバック統計 / コストを毎週 Slack に自動投稿 ([requirements.md](requirements.md) NFR-6)。
- Hermes 側の状態取得: Hermes ホストへの SSH またはHermes が `#hermes-to-brief` に発信する状態スナップショット経由 (未確定 / 要検証)。

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
