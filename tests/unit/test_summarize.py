from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic_ai.models.test import TestModel

from digest.models import Digest, Email
from digest.summarize import GeminiClient, _agent


def _make_emails(n: int) -> list[Email]:
    return [
        Email(
            id=f"email-{i}",
            sender=f"sender{i}@example.com",
            subject=f"Subject {i}",
            body_text=f"Body text {i}",
            received_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        for i in range(n)
    ]


def _output_args(tldr_count: int, detail_count: int) -> dict[str, object]:
    """TestModel の custom_output_args に渡す _DigestContent 形式の dict を返す。"""
    return {
        "tldr_items": [
            {
                "title_ja": f"タイトル{i}",
                "summary_ja": f"要約{i}",
                "source_url": f"https://example.com/{i}",
                "source_email_id": f"email-{i}",
            }
            for i in range(tldr_count)
        ],
        "details": [
            {
                "sender": f"sender{i}@example.com",
                "subject_ja": f"件名{i}",
                "points": [f"ポイント{i}-1", f"ポイント{i}-2"],
                "source_url": f"https://example.com/{i}",
                "source_email_id": f"email-{i}",
            }
            for i in range(detail_count)
        ],
    }


class TestSummarize:
    def test_returns_digest_type(self) -> None:
        with _agent.override(model=TestModel(custom_output_args=_output_args(3, 3))):
            result = GeminiClient(api_key="test").summarize(_make_emails(3), prompt="p")
        assert isinstance(result, Digest)

    def test_returns_digest_with_3_tldrs_and_3_details(self) -> None:
        with _agent.override(model=TestModel(custom_output_args=_output_args(3, 3))):
            result = GeminiClient(api_key="test").summarize(_make_emails(3), prompt="p")
        assert len(result.tldr_items) == 3
        assert len(result.details) == 3

    def test_returns_digest_with_5_tldrs(self) -> None:
        with _agent.override(model=TestModel(custom_output_args=_output_args(5, 3))):
            result = GeminiClient(api_key="test").summarize(_make_emails(5), prompt="p")
        assert len(result.tldr_items) == 5

    def test_generated_at_is_timezone_aware(self) -> None:
        with _agent.override(model=TestModel(custom_output_args=_output_args(1, 1))):
            result = GeminiClient(api_key="test").summarize(_make_emails(1), prompt="p")
        assert result.generated_at.tzinfo is not None

    def test_raises_on_invalid_output(self) -> None:
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        # 必須フィールドが欠けた dict → validation error → retry 上限超過で UnexpectedModelBehavior
        with pytest.raises(UnexpectedModelBehavior):
            with _agent.override(model=TestModel(custom_output_args={"invalid": "schema"})):
                GeminiClient(api_key="test").summarize(_make_emails(1), prompt="p")

    def test_uses_specified_model_name(self) -> None:
        # model 引数が GeminiClient.model_name より優先されることを確認
        client = GeminiClient(api_key="test", model_name="gemini-2.5-flash")
        with _agent.override(model=TestModel(custom_output_args=_output_args(1, 1))):
            result = client.summarize(_make_emails(1), prompt="p", model="gemini-2.5-pro")
        assert isinstance(result, Digest)

    def test_default_model_name_is_flash(self) -> None:
        client = GeminiClient(api_key="test")
        assert client.model_name == "gemini-2.5-flash"
