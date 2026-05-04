from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import Any

from digest.notifiers.base import Notifier
from digest.user_md_updater import UserMdDiff

logger = logging.getLogger(__name__)

_DIFF_TRUNCATE_LINES = 100
_MAX_BLOCK_CHARS = 2900  # Slack の text フィールド上限 3000 に余裕を持たせた値


def _unified_diff(before: str, after: str, filename: str) -> str:
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{filename} (before)",
            tofile=f"{filename} (after)",
            lineterm="",
            n=3,
        )
    )
    if len(lines) > _DIFF_TRUNCATE_LINES:
        omitted = len(lines) - _DIFF_TRUNCATE_LINES
        lines = lines[:_DIFF_TRUNCATE_LINES] + [f"... ({omitted} lines truncated)"]
    return "\n".join(lines)


def _diff_block(title: str, diff_text: str) -> list[dict[str, Any]]:
    if not diff_text.strip():
        return []
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}},
    ]
    # diff を _MAX_BLOCK_CHARS 文字ごとに分割して複数ブロックに収める。
    for i in range(0, len(diff_text), _MAX_BLOCK_CHARS):
        chunk = diff_text[i : i + _MAX_BLOCK_CHARS]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"```{chunk}```"}})
    return blocks


class UserdocUpdateNotifier:
    """USER.md / MEMORY.md の更新内容を Slack チャンネルに通知する。"""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def notify(
        self,
        diff: UserMdDiff,
        *,
        before_user: str,
        after_user: str,
        before_memory: str,
        after_memory: str,
        snapshot_user_path: Path,
        snapshot_memory_path: Path,
    ) -> None:
        """変更概要と before/after diff を Slack に投稿する。"""
        user_diff = _unified_diff(before_user, after_user, "USER.md")
        memory_diff = _unified_diff(before_memory, after_memory, "MEMORY.md")

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "USER.md / MEMORY.md updated"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": diff.change_summary},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Snapshot:* `{snapshot_user_path.name}` / "
                        f"`{snapshot_memory_path.name}`\n"
                        "ロールバックするには Modal Volume から"
                        "スナップショットをコピーしてください。"
                    ),
                },
            },
        ]
        blocks.extend(_diff_block("USER.md の変更", user_diff))
        blocks.extend(_diff_block("MEMORY.md の変更", memory_diff))

        self._notifier.send(
            blocks,
            text=f"[morning-brief] USER.md 更新: {diff.change_summary}",
        )
        logger.info("UserdocUpdateNotifier: sent update notification")


def build_userdoc_notifier(notifier: Notifier) -> UserdocUpdateNotifier:
    return UserdocUpdateNotifier(notifier=notifier)
