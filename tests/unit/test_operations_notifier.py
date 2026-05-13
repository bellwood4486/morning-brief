from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from digest.models import PostedMessage
from digest.operations_notifier import (
    OperationsRunSummaryNotifier,
    PhaseError,
    RunSummary,
)


class FakeNotifier:
    """send の引数を記録するテスト用 Notifier。"""

    def __init__(self) -> None:
        self.sent_blocks: list[list[dict[str, Any]]] = []
        self.sent_texts: list[str] = []

    def send(self, blocks: list[dict[str, Any]], *, text: str) -> PostedMessage:
        self.sent_blocks.append(blocks)
        self.sent_texts.append(text)
        return PostedMessage(
            channel="C_TEST",
            message_id="ts-001",
            posted_at=datetime(2026, 5, 13, 6, 30, tzinfo=UTC),
        )

    def collect_feedback(self, message_id: str) -> list[Any]:
        return []


_GENERATED_AT = datetime(2026, 5, 13, 21, 30, tzinfo=UTC)  # = 2026-05-14 06:30 JST


def _make_notifier() -> tuple[OperationsRunSummaryNotifier, FakeNotifier]:
    fake = FakeNotifier()
    return OperationsRunSummaryNotifier(notifier=fake), fake


class TestOkStatus:
    def test_send_called_once(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=3)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert len(fake.sent_blocks) == 1

    def test_fallback_text_contains_checkmark_and_count(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=5)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert "✅" in fake.sent_texts[0]
        assert "5" in fake.sent_texts[0]

    def test_first_block_is_header(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=2)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert fake.sent_blocks[0][0]["type"] == "header"

    def test_no_error_section_when_no_errors(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=2)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "エラー詳細" not in all_text

    def test_header_contains_jst_date(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=1)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        header_text = fake.sent_blocks[0][0]["text"]["text"]
        assert "2026-05-14" in header_text
        assert "JST" in header_text


class TestEmptyStatus:
    def test_fallback_text_contains_checkmark_and_no_mail_message(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="empty")
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert "✅" in fake.sent_texts[0]
        assert "対象メールなし" in fake.sent_texts[0]

    def test_status_section_contains_no_mail_message(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="empty")
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "対象メールなし" in all_text

    def test_no_error_section(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="empty")
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "エラー詳細" not in all_text


class TestErrorStatus:
    def test_fallback_text_contains_cross_mark(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(
            status="error",
            errors=[PhaseError("phase3", "API timeout")],
        )
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert "❌" in fake.sent_texts[0]

    def test_error_section_contains_phase_and_message(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(
            status="error",
            errors=[PhaseError("phase3", "API timeout")],
        )
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "phase3" in all_text
        assert "API timeout" in all_text

    def test_multiple_errors_all_appear(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(
            status="error",
            errors=[
                PhaseError("phase2", "Gmail error"),
                PhaseError("phase3", "Gemini error"),
            ],
        )
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "phase2" in all_text
        assert "Gmail error" in all_text
        assert "phase3" in all_text
        assert "Gemini error" in all_text

    def test_fallback_text_contains_phase_name(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(
            status="error",
            errors=[PhaseError("phase3", "timeout")],
        )
        notifier.notify(summary, generated_at=_GENERATED_AT)
        assert "phase3" in fake.sent_texts[0]


class TestUserdocUpdatedFlag:
    def test_userdoc_updated_true_appears_in_blocks(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=1, userdoc_updated=True)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "あり" in all_text

    def test_userdoc_updated_false_appears_in_blocks(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=1, userdoc_updated=False)
        notifier.notify(summary, generated_at=_GENERATED_AT)
        all_text = str(fake.sent_blocks[0])
        assert "なし" in all_text


class TestDryRun:
    def test_send_not_called_in_dry_run(self) -> None:
        notifier, fake = _make_notifier()
        summary = RunSummary(status="ok", digest_count=2)
        notifier.notify(summary, generated_at=_GENERATED_AT, dry_run=True)
        assert len(fake.sent_blocks) == 0

    def test_dry_run_prints_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        notifier, _ = _make_notifier()
        summary = RunSummary(status="ok", digest_count=2)
        notifier.notify(summary, generated_at=_GENERATED_AT, dry_run=True)
        captured = capsys.readouterr()
        assert "dry_run" in captured.out.lower()


class TestSendFailureSilenced:
    def test_exception_from_notifier_does_not_propagate(self) -> None:
        class BrokenNotifier:
            def send(self, blocks: list[Any], *, text: str) -> PostedMessage:
                raise RuntimeError("slack down")

            def collect_feedback(self, message_id: str) -> list[Any]:
                return []

        notifier = OperationsRunSummaryNotifier(notifier=BrokenNotifier())  # type: ignore[arg-type]
        summary = RunSummary(status="ok", digest_count=1)
        notifier.notify(summary, generated_at=_GENERATED_AT)  # should not raise
