from __future__ import annotations

from datetime import UTC, datetime

from digest.formatter import (
    digest_fallback_text,
    empty_digest_blocks,
    empty_digest_fallback_text,
    to_block_kit,
)
from digest.models import DetailItem, Digest, TldrItem


def _make_digest(
    tldr_n: int = 3,
    detail_n: int = 2,
    with_glossary: bool = True,
    points_n: int = 3,
) -> Digest:
    tldr_items = [
        TldrItem(
            title_ja=f"タイトル{i}",
            summary_ja=f"要約{i}",
            source_url=f"https://example.com/tldr/{i}",
            source_email_id=f"email-{i}",
        )
        for i in range(tldr_n)
    ]
    details = [
        DetailItem(
            sender=f"sender{i}@example.com",
            subject_ja=f"件名{i}",
            points=[f"ポイント{i}-{j}" for j in range(points_n)],
            glossary={"用語": "解説"} if with_glossary else {},
            source_url=f"https://example.com/detail/{i}",
            source_email_id=f"email-{i}",
        )
        for i in range(detail_n)
    ]
    return Digest(
        tldr_items=tldr_items,
        details=details,
        generated_at=datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC),
    )


def test_to_block_kit_starts_with_header_block() -> None:
    digest = _make_digest()
    blocks = to_block_kit(digest)
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["type"] == "plain_text"


def test_to_block_kit_renders_jst_date_in_header() -> None:
    # 2026-04-27T22:00:00 UTC = 2026-04-28T07:00:00 JST
    digest = Digest(
        tldr_items=[
            TldrItem(
                title_ja="t",
                summary_ja="s",
                source_url="https://example.com",
                source_email_id="e1",
            )
        ],
        details=[],
        generated_at=datetime(2026, 4, 27, 22, 0, 0, tzinfo=UTC),
    )
    blocks = to_block_kit(digest)
    header_text = blocks[0]["text"]["text"]
    assert "2026-04-28" in header_text
    assert "JST" in header_text


def test_to_block_kit_includes_tldr_section_with_all_items() -> None:
    digest = _make_digest(tldr_n=4)
    blocks = to_block_kit(digest)
    # header + divider + TL;DR section (index 2)
    tldr_block = blocks[2]
    assert tldr_block["type"] == "section"
    text = tldr_block["text"]["text"]
    assert "TL;DR" in text
    for i in range(4):
        assert f"タイトル{i}" in text
        assert f"要約{i}" in text
        assert f"https://example.com/tldr/{i}" in text


def test_to_block_kit_emits_one_divider_per_detail() -> None:
    detail_n = 3
    digest = _make_digest(detail_n=detail_n)
    blocks = to_block_kit(digest)
    dividers = [b for b in blocks if b["type"] == "divider"]
    # header の後 + TL;DR の後 + detail ごとに 1 個
    assert len(dividers) == 2 + detail_n


def test_to_block_kit_detail_section_has_no_accessory() -> None:
    digest = _make_digest(detail_n=2)
    blocks = to_block_kit(digest)
    for i in range(2):
        detail_section = next(b for b in blocks if b.get("block_id") == f"detail:email-{i}")
        assert "accessory" not in detail_section


def test_to_block_kit_includes_reaction_hint_for_each_detail() -> None:
    detail_n = 2
    digest = _make_digest(detail_n=detail_n)
    blocks = to_block_kit(digest)
    hint_contexts = [
        b
        for b in blocks
        if b["type"] == "context"
        and any("👍" in elem.get("text", "") for elem in b.get("elements", []))
    ]
    assert len(hint_contexts) == detail_n
    for ctx in hint_contexts:
        text = ctx["elements"][0]["text"]
        assert "👍" in text
        assert "👎" in text
        assert "🔥" in text
        assert "🔇" in text


def test_to_block_kit_omits_glossary_context_when_empty() -> None:
    digest = _make_digest(detail_n=1, with_glossary=False)
    blocks = to_block_kit(digest)
    glossary_contexts = [
        b
        for b in blocks
        if b["type"] == "context"
        and not any("👍" in elem.get("text", "") for elem in b.get("elements", []))
    ]
    assert len(glossary_contexts) == 0


def test_to_block_kit_emits_glossary_context_when_present() -> None:
    digest = _make_digest(detail_n=2, with_glossary=True)
    blocks = to_block_kit(digest)
    glossary_contexts = [
        b
        for b in blocks
        if b["type"] == "context"
        and not any("👍" in elem.get("text", "") for elem in b.get("elements", []))
    ]
    # 2 件の detail それぞれに glossary context
    assert len(glossary_contexts) == 2
    assert "用語" in glossary_contexts[0]["elements"][0]["text"]


def test_to_block_kit_skips_points_section_when_empty() -> None:
    detail = DetailItem(
        sender="s@example.com",
        subject_ja="件名",
        points=[],
        source_url="https://example.com",
        source_email_id="email-0",
    )
    digest = Digest(
        tldr_items=[
            TldrItem(
                title_ja="t",
                summary_ja="s",
                source_url="https://example.com",
                source_email_id="email-0",
            )
        ],
        details=[detail],
        generated_at=datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC),
    )
    blocks = to_block_kit(digest)
    # detail ブロック群: section(header) → context(hint) → divider (points なし)
    # points 用の section が存在しないことを検証 (header section 以外に点のない section がない)
    detail_section = next(b for b in blocks if b.get("block_id", "").startswith("detail:"))
    detail_idx = blocks.index(detail_section)
    detail_group = blocks[detail_idx:]
    sections_after_header = [b for b in detail_group[1:] if b["type"] == "section"]
    assert len(sections_after_header) == 0


def test_empty_digest_blocks_returns_header_and_no_email_notice() -> None:
    generated_at = datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC)
    blocks = empty_digest_blocks(generated_at)
    assert blocks[0]["type"] == "header"
    assert len(blocks) == 2
    notice_text = blocks[1]["text"]["text"]
    assert "本日は対象メールなし" in notice_text


def test_to_block_kit_returns_only_dicts() -> None:
    digest = _make_digest()
    blocks = to_block_kit(digest)
    assert all(isinstance(b, dict) for b in blocks)


# --- digest_fallback_text ---


def test_digest_fallback_text_contains_jst_date() -> None:
    digest = _make_digest()
    result = digest_fallback_text(digest)
    assert "2026-04-28" in result


def test_digest_fallback_text_uses_jst_not_utc() -> None:
    # UTC 22:00 = JST 翌 07:00 なので JST 日付は翌日になる。
    digest = Digest(
        tldr_items=[
            TldrItem(
                title_ja="t",
                summary_ja="s",
                source_url="https://example.com",
                source_email_id="e1",
            )
        ],
        details=[],
        generated_at=datetime(2026, 4, 27, 22, 0, 0, tzinfo=UTC),
    )
    result = digest_fallback_text(digest)
    assert "2026-04-28" in result
    assert "2026-04-27" not in result


def test_digest_fallback_text_contains_tldr_count() -> None:
    # TL;DR 件数が通知バナーで確認できることを保証する。
    digest = _make_digest(tldr_n=5)
    result = digest_fallback_text(digest)
    assert "5" in result


# --- empty_digest_fallback_text ---


def test_empty_digest_fallback_text_contains_jst_date() -> None:
    generated_at = datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC)
    result = empty_digest_fallback_text(generated_at)
    assert "2026-04-28" in result


def test_empty_digest_fallback_text_uses_jst_not_utc() -> None:
    # UTC 22:00 = JST 翌 07:00 なので JST 日付は翌日になる。
    generated_at = datetime(2026, 4, 27, 22, 0, 0, tzinfo=UTC)
    result = empty_digest_fallback_text(generated_at)
    assert "2026-04-28" in result
    assert "2026-04-27" not in result


def test_empty_digest_fallback_text_indicates_no_emails() -> None:
    generated_at = datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC)
    result = empty_digest_fallback_text(generated_at)
    assert "対象メールなし" in result
