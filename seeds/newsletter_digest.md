# newsletter_digest

**name:** newsletter_digest

**description:** 英語の技術系ニュースレターを日本語ダイジェストに変換するスキル。

**when_to_use:** `morning-brief` の Phase 3 (要約フェーズ) で `digest_job` から呼び出されるとき。

## 概要

`seeds/summarize_prompt.md` に記述したプロンプトを Gemini 2.5 Flash に渡し、
`src/digest/models.py` の `Digest` 型 (TldrItem × 3-5 件 + DetailItem × N 件) を生成する。

## 参照

- プロンプト: `seeds/summarize_prompt.md`
- 出力型契約: `src/digest/models.py` の `Digest`, `TldrItem`, `DetailItem`
- 呼び出し元: `src/digest/summarize.py` の `summarize()`

## TODO (Hermes が育てる領域)

<!-- Hermes が feedback を学習した後、以下のセクションを自動更新する想定 -->

**改善方針:** 初期版のため未記入。Sprint 2 以降のフィードバックループで更新される。

**成功例:** (Sprint 1 完了後に追記)

**失敗例:** (Sprint 1 完了後に追記)
