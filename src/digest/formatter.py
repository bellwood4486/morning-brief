from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from digest.models import DetailItem, Digest, TldrItem

_JST = ZoneInfo("Asia/Tokyo")


def digest_fallback_text(digest: Digest) -> str:
    """Slack push 通知・スクリーンリーダー用の fallback テキストを返す。"""
    date_str = digest.generated_at.astimezone(_JST).strftime("%Y-%m-%d")
    return f"Tech Newsletter Digest {date_str} (JST) — TL;DR {len(digest.tldr_items)} 件"


def empty_digest_fallback_text(generated_at: datetime) -> str:
    """対象メールなし時の fallback テキストを返す。"""
    date_str = generated_at.astimezone(_JST).strftime("%Y-%m-%d")
    return f"Tech Newsletter Digest {date_str} (JST) — 本日は対象メールなし"


def to_block_kit(digest: Digest) -> list[dict[str, Any]]:
    """Digest を Slack Block Kit の dict リストに変換する。"""
    blocks: list[dict[str, Any]] = []
    blocks.append(_header_block(digest.generated_at))
    blocks.append({"type": "divider"})
    blocks.append(_tldr_section(digest.tldr_items))
    blocks.append({"type": "divider"})
    for item in digest.details:
        blocks.extend(_detail_blocks(item))
    return blocks


def empty_digest_blocks(generated_at: datetime) -> list[dict[str, Any]]:
    """対象メールなし時のフォールバックブロックを返す。"""
    return [
        _header_block(generated_at),
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "本日は対象メールなし"},
        },
    ]


def _header_block(generated_at: datetime) -> dict[str, Any]:
    date_str = generated_at.astimezone(_JST).strftime("%Y-%m-%d")
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Tech Newsletter Digest {date_str} (JST)",
        },
    }


def _tldr_section(items: list[TldrItem]) -> dict[str, Any]:
    lines = ["*TL;DR*"]
    for item in items:
        lines.append(f"• <{item.source_url}|{item.title_ja}> — {item.summary_ja}")
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    }


def _detail_blocks(item: DetailItem) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "block_id": f"detail:{item.source_email_id}",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{item.source_url}|{item.subject_ja}>*\n_{item.sender}_",
            },
        },
    ]
    if item.points:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(f"• {p}" for p in item.points),
                },
            }
        )
    if item.glossary:
        blocks.append(_glossary_context(item.glossary))
    blocks.append(_reaction_hint_context())
    blocks.append({"type": "divider"})
    return blocks


def _glossary_context(glossary: dict[str, str]) -> dict[str, Any]:
    text = "\n".join(f"*{k}* — {v}" for k, v in glossary.items())
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": text}],
    }


def _reaction_hint_context() -> dict[str, Any]:
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "👍 役立つ / 👎 興味なし / 🔥 もっと欲しい / 🔇 送信元ミュート",
            },  # noqa: E501
        ],
    }
