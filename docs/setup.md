# Setup Guide

## 0. このドキュメントの読み方

**上から順に実行し、各章末の「成功確認」が pass したら次の章へ進む。** 詰まった場合は §14 を参照。

- 所要時間の目安: 60-90 分 (外部サービスの承認待ち込み)。
- 前提 OS: macOS。Linux でも基本は同じだが `brew` 部分は読み替えること。

## 1. 前提と前提知識

### 必要なアカウント

| サービス | 用途 | 備考 |
|---|---|---|
| Google (Gmail) | ニュースレターの受信・OAuth 認証 | 既存の Google アカウントで可 |
| Slack workspace | ダイジェストの配信先 | 個人用の新規 workspace 推奨 |
| [Modal](https://modal.com) | サーバーレス実行基盤 | 無料枠あり |
| [Google AI Studio](https://aistudio.google.com) | Gemini API key の発行 | Google アカウントと同じで可 |

### 秘匿情報の扱い

API キー・refresh token・bot token は **Modal Secrets で管理する**。リポジトリにコミットしてはいけない ([CLAUDE.md](../CLAUDE.md) §やってはいけないこと §1)。`.env` は `.gitignore` 済み。

## 2. ローカル環境の準備

mise がなければ先にインストールする。

```bash
brew install mise
```

リポジトリを clone した後、以下を実行してツール一式を揃える。

```bash
mise trust    # このリポジトリを信頼
mise install  # python 3.11, uv, just を一括インストール
```

### 成功確認

```bash
mise current  # python / uv / just が表示される
python --version  # Python 3.11.x
just --version
```

## 3. リポジトリの取得と依存導入

```bash
git clone https://github.com/bellwood4486/morning-brief.git
cd morning-brief
just sync     # uv sync を実行して依存パッケージをインストール
```

### Git hook のインストール

リポジトリ clone 直後に 1 度だけ実行:

```bash
uv run pre-commit install
```

これでコミット時に gitleaks が staged 差分を自動スキャンする。

### 成功確認

```bash
just lint       # ruff check がグリーン
just test-arch  # アーキテクチャテストがグリーン
```

> `just check` (全検証) はこの時点では `config.yaml` が未配置なので一部 fail する。§11 で再実行する。

## 4. 設定ファイル (`config.yaml`) の作成

config.yaml は **Modal Volume `morning-brief-state` 上が唯一の管理場所**。
ローカルの `./config.yaml` は作業用のコピーにすぎず、runtime (cron/dry-run) は Volume を直接読む。

初回セットアップでは、以下で Volume に config を登録する:

```bash
just config-edit
```

`config-edit` は次の処理を行う:

1. Volume から `config.yaml` を取得してエディタで開く
2. Volume に `config.yaml` が存在しない場合は `config.example.yaml` をひな形として開く
3. エディタ終了後、pydantic で schema validate してから Volume に保存する

各キーの意味:

| キー | 既定値 | 説明 |
|---|---|---|
| `gmail.label` | `Newsletter/Tech` | 対象メールに付くラベル名 |
| `gmail.processed_label` | `Newsletter/Tech/Processed` | 処理済みを示すラベル名 |
| `gmail.lookback_hours` | `24` | 何時間前までのメールを対象にするか |
| `slack.digest_channel` | `C0XXXXXXX` | ダイジェスト投稿先チャンネル ID (§6.4 参照) |
| `slack.alerts_channel` | `C0YYYYYYY` | エラー通知先チャンネル ID (§6.4 参照) |
| `slack.userdoc_channel` | `C0ZZZZZZZ` | USER.md 更新通知先チャンネル ID (§6.4 参照) |
| `llm.model` | `gemini-2.5-flash` | 使用する Gemini モデル名 |
| `schedule.cron` | `30 21 * * 1-5` | Modal Cron の設定 (UTC)。平日 06:30 JST |

チャンネル ID の取得方法は §6.4 を参照すること。

### 成功確認

```bash
just vol-get config.yaml  # Volume から取得して内容を確認
cat config.yaml
```

## 5. seed ファイルの初期記入

本番稼働前に以下を準備する。

### `seeds/user_initial.md` の記入

`seeds/user_initial.md` を開き、5 つのセクション (興味分野 / 嫌うトピック / 読み方の癖 / ミュート済み送信元 / 英語レベル) をすべて埋めること。

```bash
# テキストエディタで seeds/user_initial.md を編集
git add seeds/user_initial.md
git commit -m "chore: fill user_initial.md with personal preferences"
```

`digest_job` 起動時に `userdoc_store.bootstrap_if_missing()` が Volume に USER.md が無ければこのファイルをコピーする (ADR-015)。すでに Volume に USER.md が存在する場合は上書きされない。

Sprint 2 以降は Gemini が feedback.jsonl を元に差分を生成し、Modal Volume に直接書き込んで Slack に通知する ([agent-design.md](agent-design.md) §4.2)。

### `seeds/summarize_prompt.md`

以下の 2 箇所を必ず埋めること。

1. **役割説明のトーン** (先頭付近の `<!-- TODO -->`): 要約の文体や技術的深さの好みを記入。
2. **TL;DR 選定基準** (`### TldrItem` 付近の `<!-- TODO -->`): 優先したいトピック・除外したいカテゴリを記入。ここが空だと Gemini の判断に完全に委ねられる。

### 成功確認

```bash
just test-arch  # test_prompts_in_seeds.py がグリーン
just md-lint    # Markdown の lint がグリーン
```

## 5.5 Modal CLI 認証

`modal` は `pyproject.toml` に依存として含まれているため `just sync` でインストール済み。
初回は認証トークンを発行する。

```bash
uv run modal token new  # ブラウザが開いてログイン・トークン発行
```

## 6. Slack App の作成と Bot Token の登録

### 6.1 Slack App の作成

1. [api.slack.com/apps](https://api.slack.com/apps) を開き「**Create New App**」→「**From scratch**」を選択。
2. App Name (例: `morning-brief`) と対象 workspace を設定。

### 6.2 Bot Token Scopes の設定

左メニュー「**OAuth & Permissions**」→「**Bot Token Scopes**」に以下のスコープを追加する。

| スコープ | 用途 |
|---|---|
| `chat:write` | ダイジェストの投稿 |
| `reactions:read` | 前日のリアクション収集 |
| `channels:history` | スレッド返信の収集 |

### 6.3 Workspace へのインストールと Token 取得

「**OAuth & Permissions**」ページ上部の「**Install to Workspace**」をクリックし承認する。
表示された「**Bot User OAuth Token**」(`xoxb-` で始まる文字列) をコピーしておく。

### 6.4 チャンネルの作成と Bot の招待

Slack ワークスペースで以下の 3 チャンネルを作成する。

- `#newsletter-digest`: ダイジェストの投稿先
- `#alerts`: エラー通知先
- `#userdoc-updates`: USER.md / MEMORY.md の更新通知先 (change_summary + unified diff が届く)

各チャンネルで `/invite @<bot-name>` を実行して Bot を招待する。

チャンネル ID は Slack の「チャンネル詳細」画面の一番下に表示される (`C0XXXXXXX` 形式)。
`config.yaml` の `digest_channel` / `alerts_channel` / `userdoc_channel` にそれぞれの ID を設定する。

### 6.5 Modal Secret の登録

シェル履歴への平文露出を防ぐため、対話入力で値を渡す (`-r` は backslash エスケープを無効化、`unset` は環境変数の残留を防ぐ)。

```bash
read -rs SLACK_BOT_TOKEN
uv run modal secret create slack-bot-token SLACK_BOT_TOKEN="$SLACK_BOT_TOKEN"
unset SLACK_BOT_TOKEN
```

### 成功確認

```bash
uv run modal secret list  # slack-bot-token が表示される
```

## 7. Gmail OAuth 認証の取得と登録

### 7.1 Google Cloud Console での準備

1. [console.cloud.google.com](https://console.cloud.google.com) でプロジェクトを作成 (または既存を選択)。
2. 「**APIs & Services**」→「**Library**」で「Gmail API」を検索して有効化。
3. 「**OAuth consent screen**」を設定 (External でも Internal でも可)。Testing users に自分のアドレスを追加。

### 7.2 OAuth Client の作成

「**APIs & Services**」→「**Credentials**」→「**Create credentials**」→「**OAuth client ID**」で **Desktop app** を選択。
作成後、`credentials.json` をダウンロードしリポジトリ直下に置く (`.gitignore` 済み)。

### 7.3 OAuth フローの実行

```bash
uv run python scripts/bootstrap_oauth.py
```

ブラウザが開いて認可フローが走る。承認後:

- `gmail_oauth.json` がリポジトリ直下に生成される (`.gitignore` 済み)。
- `gmail-oauth` が Modal Secrets に自動登録される。

> **注意 — OAuth 同意画面について**: 認可画面に「メールの読み取り、構成、削除、送信」と表示されるが、
> このサービスが使うスコープは `gmail.modify` のみ (= 読み取りとラベル付け)。
> Gmail での送信は行わない ([CLAUDE.md](../CLAUDE.md) §やってはいけないこと §6、[design.md](design.md) ADR-009)。

### 成功確認

```bash
uv run modal secret list  # gmail-oauth が表示される
ls -l gmail_oauth.json  # パーミッション 600 であること
```

## 8. Gemini API key の取得と登録

[AI Studio](https://aistudio.google.com/apikey) で API key を作成する。

> **重要**: **Vertex AI ではなく AI Studio** の API key を使う。Vertex AI はサービスアカウント JSON が必要で Modal との統合が煩雑になるため採用しない ([design.md](design.md) ADR-003)。

シェル履歴への平文露出を防ぐため、対話入力で値を渡す。

```bash
read -rs GEMINI_API_KEY
uv run modal secret create gemini-api-key GEMINI_API_KEY="$GEMINI_API_KEY"
unset GEMINI_API_KEY
```

### 成功確認

```bash
uv run modal secret list  # gemini-api-key が表示される
```

## 8.5 オブザーバビリティ (Logfire) の設定 — 任意

**スキップ可**: クレデンシャルが未設定でもアプリは正常動作する。処理フロー・LLM 入出力の可視化が不要であれば §9 に進む。

設計判断の背景は [design.md ADR-010](design.md#adr-010) を参照。Logfire 1 本に統一している (LangSmith は廃止)。

### Logfire

[logfire.pydantic.dev](https://logfire.pydantic.dev) でアカウントとプロジェクトを作成する。

```bash
uv run logfire auth                        # ブラウザで認証
uv run logfire projects use morning-brief  # プロジェクトを選択
```

write token を取得して Modal Secret に登録する。

```bash
read -rs LOGFIRE_TOKEN
uv run modal secret create logfire LOGFIRE_TOKEN="$LOGFIRE_TOKEN"
unset LOGFIRE_TOKEN
```

### 成功確認

```bash
uv run modal secret list  # logfire が表示される
```

## 9. Gmail 側のラベル / フィルタ設定

> ラベルの設定は本サービスのコード責務外だが ([requirements.md](requirements.md) FR-1)、設定されていないとダイジェストが空になるためここで案内する。

### 9.1 ラベルの作成

Gmail の左サイドバー下部「ラベルを作成」で以下を作成する (ネスト構造)。

- `Newsletter` → `Newsletter/Tech`
- `Newsletter` → `Newsletter/Tech` → `Newsletter/Tech/Processed`

### 9.2 フィルタの設定

「設定」→「フィルタとブロック中のアドレス」→「新しいフィルタを作成」で、対象ニュースレターの送信元アドレスを条件に `Newsletter/Tech` ラベルを自動付与するフィルタを作る。

例: Bytes を購読している場合

- 「From」に `bytes.dev` を含む条件を設定
- アクション: `Newsletter/Tech` ラベルを付ける

購読するニュースレターごとにフィルタを追加する。

### 成功確認

Gmail 検索ボックスで以下を実行し、対象のメールが表示されることを確認する。

```text
label:Newsletter/Tech is:unread newer_than:1d
```

## 10. Volume 作成と最終確認

`modal_app.py` は `create_if_missing=True` で起動時に Volume を自動作成するが、事前に明示的に作ることで確認がしやすい。

```bash
uv run modal volume create morning-brief-state
```

### 成功確認

```bash
uv run modal volume list  # morning-brief-state が表示される
uv run modal secret list  # slack-bot-token / gmail-oauth / gemini-api-key の 3 つが表示される
```

## 11. ドライラン (本番手前の動作確認)

Slack に投稿せず、最終的な Markdown を stdout に出力するモードで動作確認する。

```bash
just dry-run  # = uv run modal run modal_app.py::digest_job --dry-run
```

> **config の変更方法**: `config.yaml` を変更したいときは `just config-edit`。
> Volume が真なので、保存すれば次の `just dry-run` / `just run` から即時反映される。
> 低レベル操作として `just vol-get config.yaml` (Volume → ローカルに取得) /
> `just vol-put config.yaml` (ローカル → Volume に validate してアップロード) も使える。

期待動作:

- TL;DR + 詳細セクションを含む Markdown が stdout に出力される。
- Slack の `#newsletter-digest` には何も投稿されない。
- Gmail のラベルも変更されない。

### 成功確認

stdout に TL;DR と詳細セクションが出力されること。エラーが出た場合は §14 を参照。

```bash
just check  # 全検証を一括実行 (lint / fmt-check / type / test / test-arch / md-lint)
```

## 12. 本番投入 (Cron 有効化)

Modal にアプリをデプロイして Cron を有効化する。

```bash
uv run modal deploy modal_app.py
```

### 成功確認

```bash
uv run modal app list  # morning-brief が deployed 表示される
```

[Modal ダッシュボード](https://modal.com/apps) で `morning-brief` アプリを開き、次回 Cron 起動時刻が表示されることを確認する。

最初の自動実行を待たずに今すぐ動かしたい場合:

```bash
just run  # = uv run modal run modal_app.py::digest_job
```

## 13. CI/CD 自動化

### 13.1 GitHub Secrets の登録 (自動デプロイに必要)

main への push (PR merge 含む) が `check` job を通過すると、自動で `modal deploy` が走る。
そのために Modal トークンを GitHub Secrets に登録する。

Modal トークンを確認する:

```bash
cat ~/.modal.toml
```

`token_id` と `token_secret` をメモし、以下の手順で GitHub に登録する:

1. GitHub リポジトリの **Settings → Secrets and variables → Actions** を開く
2. **New repository secret** でそれぞれ登録:
   - 名前 `MODAL_TOKEN_ID`: `~/.modal.toml` の `token_id` の値
   - 名前 `MODAL_TOKEN_SECRET`: `~/.modal.toml` の `token_secret` の値

### 成功確認

PR を merge し、GitHub Actions で `deploy` job が緑になることを確認する。
[Modal ダッシュボード](https://modal.com/apps) でデプロイ済みリビジョンの commit SHA が一致すること。

### 13.2 Renovate のセットアップ (依存自動更新)

[Renovate GitHub App](https://github.com/apps/renovate) をこの repo に install すると、
`renovate.json` の設定に従って依存更新 PR を自動作成する。

- **毎週月曜 UTC 06:00 前**: 各ライブラリの最新版 PR (pydantic 系・Google クライアント・dev ツールはグループ化)
- **毎月 1 日 UTC 06:00 前**: `uv.lock` 全体更新 PR (lockFileMaintenance)

#### install 手順

1. [https://github.com/apps/renovate](https://github.com/apps/renovate) → **Install**
2. **Only select repositories** でこの repo を選択 → **Install**

install 後、Renovate が自動でオンボーディング PR を作成する。内容を確認して merge すると有効化される。

## 14. Sprint 1 完了基準のチェックリスト

以下がすべて満たされれば Sprint 1 完了。

- [ ] 平日 06:30 JST に `#newsletter-digest` にダイジェストが自動投稿される
- [ ] ダイジェストは TL;DR + 詳細の 2 段構え
- [ ] 各記事ブロックに 👍/👎/🔥/🔇 リアクション促しが付いている (Sprint 1 当初は `[ミュート]` ボタンも付いていたが Sprint 2 で削除)
- [ ] `uv run pre-commit run --all-files` がグリーン (リポジトリに秘匿情報がない)
- [ ] `just check` 全体がグリーン
- [ ] GitHub Actions の `check` job がグリーン (PR 作成時に自動確認)

実機での動作確認 (ドライランから本番投稿まで) はこのチェックリストで完了とみなす。

## 15. トラブルシューティング / FAQ

### OAuth 同意画面に「メールの送信」と表示される

仕様。`gmail.modify` スコープは Google の UI 上では「送信」を含む表示になるが、
本サービスのコードは Gmail への送信を行わない (§7.3 注意事項参照)。

### `just dry-run` で `config.yaml: No such file or directory` エラー

```bash
cp config.example.yaml config.yaml
```

### `just dry-run` で `SLACK_BOT_TOKEN: KeyError`

Modal Secrets が登録されていない。§6-§8 の登録手順を確認すること。

### pre-commit の gitleaks で誤検知が出る

`.gitleaks.toml` の `allowlist` を確認し、テスト用のダミートークンや既知の誤検知パターンを追加する。

### `just dry-run` でメールが 0 件

- §9 のフィルタ設定で `Newsletter/Tech` ラベルが付いているか確認。
- `config.yaml` の `gmail.lookback_hours` を伸ばして再試行 (例: `48`)。
- Gmail 検索で `label:Newsletter/Tech is:unread` を実行し、未処理のメールが存在するか確認。

### Modal Volume が複数できてしまった

```bash
uv run modal volume list  # 一覧確認
uv run modal volume delete <不要な Volume 名>  # 余分なものを削除
```
