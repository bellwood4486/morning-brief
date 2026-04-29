# morning-brief

Gmail に届く英語のテック系ニュースレターを Gemini で日本語要約し、平日朝 6:30 (JST) に Slack へ配信する個人向け ambient agent です。Modal 上でサーバーレスに動作し、Hermes Agent によって配信内容がユーザー好みへ徐々に最適化されていきます。

## 何が嬉しいか

- **通勤時に英語ニュースレターを片手で消化できる** — TL;DR (3-5 本) を流し読みし、気になる記事だけ原文 URL に 1 タップ。
- **リアクション 1 タップで自分仕様に育つ** — 文章を書かなくても 👍 / 👎 / 🔥 / `[ミュート]` ボタンで好みが伝わり、Hermes が USER.md と skills を翌日以降に反映する。
- **ambient agent + serverless + 自動学習ループの参照実装** — Modal Volume での永続化、HITL の翌朝 polling、Hermes による skill 自動成長を 1 リポジトリで読み解ける。

## 想定読者

ambient agent / Modal / Hermes に関心のある開発者。日々の運用に使う「自分用ツール」であると同時に、これらの技術をまとめて触ってみたい人向けの「参照実装」として公開しています。

## アーキテクチャ

```text
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
| Modal | 実行環境、Cron、Volume、Secrets | CLI token |

## 配信構造

ダイジェストは 2 段構え:

1. **TL;DR ブロック** — 3-5 本のヘッドライン (日本語タイトル + 1 行サマリ + 原文リンク)
2. **詳細ブロック** — 1 メールにつき 1 ブロック。要点 3 つ + 専門用語注 + 原文リンク。各ブロックに 👍 / 👎 / 🔥 のリアクション促し note と `[ミュート]` ボタンが付く

## クイックスタート

詳細手順は **[docs/setup.md](docs/setup.md)** を参照 (60-90 分、macOS 想定)。最短経路:

```bash
# 前提: mise がなければ `brew install mise`
mise trust && mise install   # python / uv / just / gitleaks
just sync                    # 依存インストール
just check                   # lint / type / test / secrets
just dry-run                 # Slack には送らず最終 Markdown を stdout に出す
```

Modal / Slack / Gmail / Gemini の API key 発行と Modal Secrets 登録は `docs/setup.md` に手順がある。

## ディレクトリ構成

主要ファイルだけ抜粋 (フルツリーは [CLAUDE.md](CLAUDE.md) 参照):

```text
morning-brief/
├── modal_app.py          # Modal エントリ (Cron + digest_job)
├── src/digest/
│   ├── gmail_client.py   # 受信専用
│   ├── summarize.py      # Gemini 呼び出し
│   ├── formatter.py      # Block Kit 生成
│   ├── feedback.py       # リアクション/返信のパース
│   ├── hermes_bridge.py  # Hermes との橋渡し
│   └── notifiers/        # Notifier Protocol + SlackNotifier
├── seeds/                # 要約プロンプト・Hermes スキル定義・USER.md 初期版
└── docs/                 # requirements / design / tasks / agent-design / setup
```

## ドキュメント

- 機能要件・非機能要件: [docs/requirements.md](docs/requirements.md)
- 設計と ADR: [docs/design.md](docs/design.md)
- タスク分解と受入条件: [docs/tasks.md](docs/tasks.md)
- Hermes エージェント仕様: [docs/agent-design.md](docs/agent-design.md)
- 初回セットアップ手順: [docs/setup.md](docs/setup.md)
- 開発時の運用マニュアル (Claude Code 用): [CLAUDE.md](CLAUDE.md)

## Non-goals

このプロジェクトが**やらないこと**:

- 完全自動化しない — HITL ループを回すこと自体が学習目的の一部
- 全文翻訳しない — 要約のみ。深く読みたければ原文 URL へ
- マルチユーザー化しない — 個人 1 名運用
- 週末配信しない — 平日 06:30 JST のみ

## License

MIT License. 詳細は [LICENSE](LICENSE) を参照。
