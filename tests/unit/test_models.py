from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from digest.models import (
    DetailItem,
    Digest,
    Email,
    Feedback,
    PostedMessage,
    TldrItem,
)

_NOW = datetime(2024, 1, 1, 6, 30, 0, tzinfo=UTC)


def _email(**kwargs: object) -> Email:
    defaults: dict[str, object] = {
        "id": "msg001",
        "sender": "newsletter@example.com",
        "subject": "Weekly Tech Digest",
        "body_text": "Hello world",
        "received_at": _NOW,
    }
    defaults.update(kwargs)
    return Email(**defaults)  # type: ignore[arg-type]


def _tldr() -> TldrItem:
    return TldrItem(
        title_ja="タイトル",
        summary_ja="要約です",
        source_url="https://example.com",
        source_email_id="msg001",
    )


def _detail() -> DetailItem:
    return DetailItem(
        sender="newsletter@example.com",
        subject_ja="件名訳",
        points=["ポイント1", "ポイント2", "ポイント3"],
        source_url="https://example.com",
        source_email_id="msg001",
    )


# --- Email ---


def test_email_valid() -> None:
    email = _email()
    assert email.id == "msg001"
    assert email.links == []
    assert email.body_html is None


def test_email_links_populated() -> None:
    email = _email(links=["https://a.com", "https://b.com"])
    assert len(email.links) == 2


def test_email_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        _email(received_at=datetime(2024, 1, 1, 6, 30, 0))


def test_email_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        _email(foo="bar")  # type: ignore[call-overload]


def test_email_frozen() -> None:
    email = _email()
    with pytest.raises(ValidationError):
        email.id = "other"  # type: ignore[misc]


# --- TldrItem ---


def test_tldr_item_valid() -> None:
    item = _tldr()
    assert item.title_ja == "タイトル"


# --- DetailItem ---


def test_detail_item_glossary_typing() -> None:
    item = DetailItem(
        sender="s@example.com",
        subject_ja="件名",
        points=["p1"],
        glossary={"K8s": "Kubernetes の略"},
        source_url="https://example.com",
        source_email_id="msg001",
    )
    assert item.glossary["K8s"] == "Kubernetes の略"


def test_detail_item_glossary_wrong_type_rejected() -> None:
    with pytest.raises(ValidationError):
        DetailItem(
            sender="s@example.com",
            subject_ja="件名",
            points=["p1"],
            glossary={"K8s": 1},  # type: ignore[dict-item]
            source_url="https://example.com",
            source_email_id="msg001",
        )


# --- Digest ---


def test_digest_compose() -> None:
    digest = Digest(
        tldr_items=[_tldr()],
        details=[_detail()],
        generated_at=_NOW,
    )
    assert len(digest.tldr_items) == 1
    assert len(digest.details) == 1


def test_digest_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        Digest(
            tldr_items=[_tldr()],
            details=[_detail()],
            generated_at=datetime(2024, 1, 1, 6, 30, 0),
        )


# --- Feedback ---


@pytest.mark.parametrize("kind", ["reaction", "button", "thread_reply"])
def test_feedback_kind_literal(kind: str) -> None:
    fb = Feedback(kind=kind, target_email_id="msg001", value="👍")  # type: ignore[arg-type]
    assert fb.kind == kind


def test_feedback_invalid_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        Feedback(kind="invalid", target_email_id="msg001", value="x")  # type: ignore[arg-type]


def test_feedback_raw_dict() -> None:
    fb = Feedback(
        kind="reaction",
        target_email_id="msg001",
        value="👍",
        raw={"event_ts": "1700000000.0"},
    )
    assert fb.raw["event_ts"] == "1700000000.0"


# --- PostedMessage ---


def test_posted_message_valid() -> None:
    msg = PostedMessage(channel="#newsletter-digest", message_id="ts123", posted_at=_NOW)
    assert msg.channel == "#newsletter-digest"


def test_posted_message_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        PostedMessage(
            channel="#newsletter-digest",
            message_id="ts123",
            posted_at=datetime(2024, 1, 1, 6, 30, 0),
        )
