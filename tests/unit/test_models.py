from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from digest.models import (
    ButtonFeedback,
    DetailItem,
    Digest,
    Email,
    Feedback,
    PostedMessage,
    ReactionFeedback,
    ThreadReplyFeedback,
    TldrItem,
)

_NOW = datetime(2024, 1, 1, 6, 30, 0, tzinfo=UTC)


# 責務: 有効な Email のデフォルトを返すファクトリ。テストは差分だけ kwargs で上書きする。
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


# 責務: 有効な TldrItem のデフォルトを返すファクトリ。
def _tldr() -> TldrItem:
    return TldrItem(
        title_ja="タイトル",
        summary_ja="要約です",
        source_url="https://example.com",
        source_email_id="msg001",
    )


# 責務: 有効な DetailItem のデフォルトを返すファクトリ。
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
    """frozen=True により属性への代入が ValidationError になることを確認。"""
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


def test_reaction_feedback_valid() -> None:
    fb = ReactionFeedback(kind="reaction", message_id="ts123", emoji="thumbsup", user="U1")
    assert fb.kind == "reaction"
    assert fb.message_id == "ts123"
    assert fb.emoji == "thumbsup"
    assert fb.user == "U1"
    assert fb.raw == {}


def test_thread_reply_feedback_valid() -> None:
    fb = ThreadReplyFeedback(
        kind="thread_reply", message_id="ts123", text="良い記事でした", user="U1"
    )
    assert fb.kind == "thread_reply"
    assert fb.text == "良い記事でした"


def test_button_feedback_valid() -> None:
    fb = ButtonFeedback(
        kind="button",
        message_id="ts123",
        target_email_id="msg001",
        action_id="mute_newsletter@example.com",
        user="U1",
    )
    assert fb.kind == "button"
    assert fb.target_email_id == "msg001"
    assert fb.action_id == "mute_newsletter@example.com"


def test_reaction_feedback_rejects_target_email_id() -> None:
    # ReactionFeedback は email を対象にしない仕様。extra="forbid" でフィールド追加を弾く。
    with pytest.raises(ValidationError):
        ReactionFeedback(  # type: ignore[call-overload]
            kind="reaction",
            message_id="ts123",
            emoji="thumbsup",
            user="U1",
            target_email_id="msg001",
        )


def test_button_feedback_requires_target_email_id() -> None:
    with pytest.raises(ValidationError):
        ButtonFeedback(  # type: ignore[call-overload]
            kind="button", message_id="ts123", action_id="mute_x", user="U1"
        )


def test_feedback_discriminator_dispatches_by_kind() -> None:
    # TypeAdapter は型エイリアスや union 型の validate_python を可能にする Pydantic ユーティリティ。
    adapter = TypeAdapter(Feedback)
    reaction = adapter.validate_python(
        {"kind": "reaction", "message_id": "ts123", "emoji": "thumbsup", "user": "U1"}
    )
    assert isinstance(reaction, ReactionFeedback)

    button = adapter.validate_python(
        {
            "kind": "button",
            "message_id": "ts123",
            "target_email_id": "msg001",
            "action_id": "mute_x",
            "user": "U1",
        }
    )
    assert isinstance(button, ButtonFeedback)


def test_feedback_invalid_kind_rejected() -> None:
    adapter = TypeAdapter(Feedback)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "unknown", "message_id": "ts123"})


def test_feedback_raw_dict_round_trip() -> None:
    fb = ReactionFeedback(
        kind="reaction",
        message_id="ts123",
        emoji="thumbsup",
        user="U1",
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
