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
mise install  # python 3.11, uv, just, gitleaks を一括インストール
```

### 成功確認

```bash
mise current  # python / uv / just / gitleaks が表示される
python --version  # Python 3.11.x
just --version
gitleaks version
```

## 3. リポジトリの取得と依存導入

```bash
git clone https://github.com/bellwood4486/morning-brief.git
cd morning-brief
just sync     # uv sync を実行して依存パッケージをインストール
```

### 成功確認

```bash
just lint       # ruff check がグリーン
just test-arch  # アーキテクチャテストがグリーン
```

> `just check` (全検証) はこの時点では `config.yaml` が未配置なので一部 fail する。§11 で再実行する。

## 4. 設定ファイル (`config.yaml`) の作成

```bash
cp config.example.yaml config.yaml
```

各キーの意味:

| キー | 既定値 | 説明 |
|---|---|---|
| `gmail.label` | `Newsletter/Tech` | 対象メールに付くラベル名 |
| `gmail.processed_label` | `Newsletter/Tech/Processed` | 処理済みを示すラベル名 |
| `gmail.lookback_hours` | `24` | 何時間前までのメールを対象にするか |
| `slack.digest_channel` | `#newsletter-digest` | ダイジェスト投稿先チャンネル |
| `slack.alerts_channel` | `#alerts` | エラー通知先チャンネル |
| `llm.model` | `gemini-2.5-flash` | 使用する Gemini モデル名 |
| `schedule.cron` | `30 21 * * 1-5` | Modal Cron の設定 (UTC)。平日 06:30 JST |

Slack チャンネル名は §6 で作成するものと合わせること。

### 成功確認

```bash
just lint  # config.yaml に構文エラーがないこと
```

## 5. seed ファイルの初期記入

本番稼働前に以下の 2 ファイルに記入する。`seeds/newsletter_digest.md` は **触らない** (Hermes が育てる領域。[agent-design.md](agent-design.md) §4.3 参照)。

### `seeds/user_initial.md`

4 つの `<!-- TODO -->` セクション (興味分野 / 嫌うトピック / 読み方の癖 / 英語レベル) を埋める。ミュート済み送信元セクションは Hermes が自動追記するので空欄のまま。

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

Slack ワークスペースで以下の 2 チャンネルを作成する。

- `#newsletter-digest`: ダイジェストの投稿先
- `#alerts`: エラー通知先

各チャンネルで `/invite @<bot-name>` を実行して Bot を招待する。

### 6.5 Modal Secret の登録

```bash
uv run modal secret create slack-bot-token SLACK_BOT_TOKEN=xoxb-xxxx...
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
- stdout に `modal secret create gmail-oauth GMAIL_OAUTH_JSON=...` 形式のコマンドが表示される。

そのコマンドをコピペして実行する。

```bash
uv run modal secret create gmail-oauth GMAIL_OAUTH_JSON=<スクリプトが出力した値>
```

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

```bash
uv run modal secret create gemini-api-key GEMINI_API_KEY=AIza...
```

### 成功確認

```bash
uv run modal secret list  # gemini-api-key が表示される
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
uv run modal volume create morning-brief-hermes
```

### 成功確認

```bash
uv run modal volume list  # morning-brief-hermes が表示される
uv run modal secret list  # slack-bot-token / gmail-oauth / gemini-api-key の 3 つが表示される
```

## 11. ドライラン (本番手前の動作確認)

Slack に投稿せず、最終的な Markdown を stdout に出力するモードで動作確認する。

```bash
just dry-run  # = uv run modal run modal_app.py::digest_job --dry-run
```

期待動作:

- TL;DR + 詳細セクションを含む Markdown が stdout に出力される。
- Slack の `#newsletter-digest` には何も投稿されない。
- Gmail のラベルも変更されない。

### 成功確認

stdout に TL;DR と詳細セクションが出力されること。エラーが出た場合は §14 を参照。

```bash
just check  # 全検証を一括実行 (lint / fmt-check / type / test / test-arch / secrets / md-lint)
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

## 13. Sprint 1 完了基準のチェックリスト

以下がすべて満たされれば Sprint 1 完了。

- [ ] 平日 06:30 JST に `#newsletter-digest` にダイジェストが自動投稿される
- [ ] ダイジェストは TL;DR + 詳細の 2 段構え
- [ ] 各記事ブロックに 👍/👎/🔥 リアクション促し + `[ミュート]` ボタンが付いている
- [ ] `just secrets` がグリーン (リポジトリに秘匿情報がない)
- [ ] `just check` 全体がグリーン

実機での動作確認 (ドライランから本番投稿まで) はこのチェックリストで完了とみなす。

## 14. トラブルシューティング / FAQ

### OAuth 同意画面に「メールの送信」と表示される

仕様。`gmail.modify` スコープは Google の UI 上では「送信」を含む表示になるが、
本サービスのコードは Gmail への送信を行わない (§7.3 注意事項参照)。

### `just dry-run` で `config.yaml: No such file or directory` エラー

```bash
cp config.example.yaml config.yaml
```

### `just dry-run` で `SLACK_BOT_TOKEN: KeyError`

Modal Secrets が登録されていない。§6-§8 の登録手順を確認すること。

### `just secrets` (gitleaks) で誤検知が出る

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

### `gitleaks` が未インストールでエラーになる

```bash
mise install  # .mise.toml に従って gitleaks を含む全ツールを再インストール
```
