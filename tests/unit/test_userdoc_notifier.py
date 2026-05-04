from __future__ import annotations

from pathlib import Path
from typing import Any

from digest.models import PostedMessage
from digest.user_md_updater import UserMdDiff
from digest.userdoc_notifier import UserdocUpdateNotifier, _unified_diff


def _make_diff(summary: str = "興味分野を更新") -> UserMdDiff:
    return UserMdDiff(
        user_md_content="# USER.md\n\n更新後。\n",
        memory_md_content="# Memory Index\n",
        change_summary=summary,
    )


class FakeNotifier:
    """send の引数を記録するテスト用 Notifier。"""

    def __init__(self) -> None:
        self.sent_blocks: list[list[dict[str, Any]]] = []
        self.sent_texts: list[str] = []

    def send(self, blocks: list[dict[str, Any]], *, text: str) -> PostedMessage:
        from datetime import UTC, datetime

        self.sent_blocks.append(blocks)
        self.sent_texts.append(text)
        return PostedMessage(
            channel="C_TEST",
            message_id="ts-001",
            posted_at=datetime(2026, 5, 3, 6, 30, tzinfo=UTC),
        )

    def collect_feedback(self, message_id: str) -> list[Any]:
        return []


class TestUnifiedDiff:
    def test_empty_when_no_change(self) -> None:
        result = _unified_diff("same\n", "same\n", "FILE.md")
        assert result == ""

    def test_contains_added_line(self) -> None:
        result = _unified_diff("line1\n", "line1\nline2\n", "FILE.md")
        assert "+line2" in result

    def test_contains_removed_line(self) -> None:
        result = _unified_diff("line1\nline2\n", "line1\n", "FILE.md")
        assert "-line2" in result

    def test_truncated_when_too_long(self) -> None:
        before = "\n".join(f"line{i}" for i in range(200))
        after = "\n".join(f"new{i}" for i in range(200))
        result = _unified_diff(before, after, "FILE.md")
        assert "truncated" in result


class TestUserdocUpdateNotifier:
    def _make_notifier(self) -> tuple[UserdocUpdateNotifier, FakeNotifier]:
        fake = FakeNotifier()
        notifier = UserdocUpdateNotifier(notifier=fake)
        return notifier, fake

    def test_calls_send_once(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff()
        snap_user = tmp_path / "USER.md.20260503T063000Z.md"
        snap_memory = tmp_path / "MEMORY.md.20260503T063000Z.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧\n",
            after_user=diff.user_md_content,
            before_memory="",
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        assert len(fake.sent_blocks) == 1

    def test_blocks_contain_change_summary(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff("コーヒー関連のトピックへの興味が強まった")
        snap_user = tmp_path / "snap_user.md"
        snap_memory = tmp_path / "snap_memory.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧\n",
            after_user=diff.user_md_content,
            before_memory="",
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        all_text = str(fake.sent_blocks[0])
        assert "コーヒー関連" in all_text

    def test_blocks_contain_snapshot_filename(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff()
        snap_user = tmp_path / "USER.md.20260503T063000Z.md"
        snap_memory = tmp_path / "MEMORY.md.20260503T063000Z.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧\n",
            after_user=diff.user_md_content,
            before_memory="",
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        all_text = str(fake.sent_blocks[0])
        assert "USER.md.20260503T063000Z.md" in all_text

    def test_blocks_contain_diff_hunk(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff()
        snap_user = tmp_path / "snap_user.md"
        snap_memory = tmp_path / "snap_memory.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧 USER.md\n",
            after_user="# 新 USER.md\n",
            before_memory="",
            after_memory="",
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        all_text = str(fake.sent_blocks[0])
        assert "旧 USER.md" in all_text or "新 USER.md" in all_text

    def test_first_block_is_header(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff()
        snap_user = tmp_path / "snap_user.md"
        snap_memory = tmp_path / "snap_memory.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧\n",
            after_user=diff.user_md_content,
            before_memory="",
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        first_block = fake.sent_blocks[0][0]
        assert first_block["type"] == "header"

    def test_fallback_text_contains_summary(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff("ミュート追加")
        snap_user = tmp_path / "snap_user.md"
        snap_memory = tmp_path / "snap_memory.md"
        notifier.notify(
            diff=diff,
            before_user="# 旧\n",
            after_user=diff.user_md_content,
            before_memory="",
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        assert "ミュート追加" in fake.sent_texts[0]

    def test_no_diff_blocks_when_content_unchanged(self, tmp_path: Path) -> None:
        notifier, fake = self._make_notifier()
        diff = _make_diff()
        snap_user = tmp_path / "snap_user.md"
        snap_memory = tmp_path / "snap_memory.md"
        content = "# 変わらない\n"
        notifier.notify(
            diff=diff,
            before_user=content,
            after_user=content,
            before_memory="",
            after_memory="",
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        # diff ブロックがなくても送信自体は行われる (change_summary はある)
        assert len(fake.sent_blocks) == 1
