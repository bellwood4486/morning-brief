from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from digest.models import Digest, Email
from digest.summarize import GeminiClient


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


def _make_digest_json(tldr_count: int, detail_count: int) -> str:
    return json.dumps(
        {
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
            "generated_at": "2024-01-01T00:00:00+00:00",
        },
        ensure_ascii=False,
    )


def _make_client(
    mocker: MockerFixture,
    response_text: str | None = None,
) -> tuple[GeminiClient, MagicMock]:
    fake_genai: MagicMock = mocker.MagicMock()
    fake_response: MagicMock = MagicMock()
    fake_response.text = response_text if response_text is not None else _make_digest_json(3, 3)
    fake_genai.models.generate_content.return_value = fake_response
    return GeminiClient(client=fake_genai), fake_genai


class TestSummarize:
    def test_calls_gemini_once(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        client.summarize(_make_emails(3), prompt="test prompt")
        fake_genai.models.generate_content.assert_called_once()

    def test_passes_prompt_as_system_instruction(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        prompt = "my system prompt"
        client.summarize(_make_emails(3), prompt=prompt)
        config = fake_genai.models.generate_content.call_args.kwargs["config"]
        assert config.system_instruction == prompt

    def test_passes_emails_as_json_contents(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        emails = _make_emails(3)
        client.summarize(emails, prompt="prompt")
        contents = fake_genai.models.generate_content.call_args.kwargs["contents"]
        parsed = json.loads(contents)
        assert len(parsed) == 3
        assert [item["id"] for item in parsed] == [e.id for e in emails]

    def test_uses_default_model(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        client.summarize(_make_emails(1), prompt="p")
        assert fake_genai.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-flash"

    def test_uses_specified_model(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        client.summarize(_make_emails(1), prompt="p", model="gemini-2.5-pro")
        assert fake_genai.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-pro"

    def test_returns_digest_type(self, mocker: MockerFixture) -> None:
        client, _ = _make_client(mocker)
        result = client.summarize(_make_emails(3), prompt="p")
        assert isinstance(result, Digest)

    def test_returns_digest_with_3_tldrs_and_3_details(self, mocker: MockerFixture) -> None:
        client, _ = _make_client(mocker, response_text=_make_digest_json(3, 3))
        result = client.summarize(_make_emails(3), prompt="p")
        assert len(result.tldr_items) == 3
        assert len(result.details) == 3

    def test_returns_digest_with_5_tldrs(self, mocker: MockerFixture) -> None:
        client, _ = _make_client(mocker, response_text=_make_digest_json(5, 3))
        result = client.summarize(_make_emails(5), prompt="p")
        assert len(result.tldr_items) == 5

    def test_uses_application_json_mime_type(self, mocker: MockerFixture) -> None:
        client, fake_genai = _make_client(mocker)
        client.summarize(_make_emails(1), prompt="p")
        config = fake_genai.models.generate_content.call_args.kwargs["config"]
        assert config.response_mime_type == "application/json"

    def test_raises_when_response_text_none(self, mocker: MockerFixture) -> None:
        fake_genai: MagicMock = mocker.MagicMock()
        fake_response: MagicMock = MagicMock()
        fake_response.text = None
        fake_genai.models.generate_content.return_value = fake_response
        client = GeminiClient(client=fake_genai)
        with pytest.raises(RuntimeError, match="no text"):
            client.summarize(_make_emails(1), prompt="p")

    def test_raises_on_invalid_json(self, mocker: MockerFixture) -> None:
        from pydantic import ValidationError

        client, _ = _make_client(mocker, response_text='{"invalid": "schema"}')
        with pytest.raises(ValidationError):
            client.summarize(_make_emails(1), prompt="p")
