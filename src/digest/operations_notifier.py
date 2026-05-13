from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from digest.notifiers.base import Notifier

logger = logging.getLogger(__name__)

_JST_OFFSET_HOURS = 9


@dataclass
class PhaseError:
    phase: str
    message: str


@dataclass
class RunSummary:
    status: Literal["ok", "empty", "error"]
    digest_count: int = 0
    digest_message_id: str | None = None
    userdoc_updated: bool = False
    errors: list[PhaseError] = field(default_factory=list)


def _jst_label(dt: datetime) -> str:
    jst = dt.astimezone(UTC).replace(tzinfo=UTC)
    jst_dt = jst + timedelta(hours=_JST_OFFSET_HOURS)
    return jst_dt.strftime("%Y-%m-%d %H:%M JST")


def _build_blocks(summary: RunSummary, generated_at: datetime) -> list[dict[str, Any]]:
    label = _jst_label(generated_at)

    if summary.status == "ok":
        status_text = f"✅ *{summary.digest_count} 件配信*"
    elif summary.status == "empty":
        status_text = "✅ *対象メールなし*"
    else:
        status_text = "❌ *エラー発生*"

    userdoc_text = "USER.md 更新: *あり*" if summary.userdoc_updated else "USER.md 更新: なし"

    fields: list[dict[str, Any]] = [
        {"type": "mrkdwn", "text": status_text},
        {"type": "mrkdwn", "text": userdoc_text},
    ]

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"morning-brief 実行サマリ ({label})"},
        },
        {"type": "section", "fields": fields},
    ]

    if summary.errors:
        error_lines = "\n".join(f"• *{e.phase}*: {e.message}" for e in summary.errors)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*エラー詳細*\n{error_lines}"},
            }
        )

    return blocks


def _build_fallback_text(summary: RunSummary, generated_at: datetime) -> str:
    label = _jst_label(generated_at)
    if summary.status == "ok":
        return f"[morning-brief] ✅ 実行成功: {summary.digest_count} 件配信 ({label})"
    elif summary.status == "empty":
        return f"[morning-brief] ✅ 実行成功: 対象メールなし ({label})"
    else:
        phases = ", ".join(e.phase for e in summary.errors)
        return f"[morning-brief] ❌ 実行エラー: {phases} ({label})"


class OperationsRunSummaryNotifier:
    """digest_job の実行サマリを operations チャンネルに通知する。"""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def notify(
        self,
        summary: RunSummary,
        *,
        generated_at: datetime | None = None,
        dry_run: bool = False,
    ) -> None:
        """実行サマリを Slack に投稿する。dry_run=True の場合は stdout に出力して終了する。"""
        ts = generated_at or datetime.now(tz=UTC)
        blocks = _build_blocks(summary, ts)
        text = _build_fallback_text(summary, ts)

        if dry_run:
            print("=== OperationsRunSummary (dry_run) ===")
            print(f"fallback_text: {text}")
            print(json.dumps(blocks, ensure_ascii=False, indent=2))
            logger.info("OperationsRunSummaryNotifier: dry_run=True, skip send")
            return

        try:
            self._notifier.send(blocks, text=text)
            logger.info("OperationsRunSummaryNotifier: sent summary status=%s", summary.status)
        except Exception:
            logger.exception("OperationsRunSummaryNotifier: failed to send summary")


def build_operations_run_summary_notifier(
    notifier: Notifier,
) -> OperationsRunSummaryNotifier:
    return OperationsRunSummaryNotifier(notifier=notifier)
