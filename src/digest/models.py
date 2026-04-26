from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _check_aware(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return v


class Email(_StrictModel):
    id: str
    sender: str
    subject: str
    body_text: str
    body_html: str | None = None
    received_at: datetime
    links: list[str] = []

    @field_validator("received_at")
    @classmethod
    def _received_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)


class TldrItem(_StrictModel):
    title_ja: str
    summary_ja: str
    source_url: str
    source_email_id: str


class DetailItem(_StrictModel):
    sender: str
    subject_ja: str
    points: list[str]
    glossary: dict[str, str] = {}
    source_url: str
    source_email_id: str


class Digest(_StrictModel):
    tldr_items: list[TldrItem]
    details: list[DetailItem]
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def _generated_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)


class Feedback(_StrictModel):
    kind: Literal["reaction", "button", "thread_reply"]
    target_email_id: str
    value: str
    raw: dict[str, Any] = {}


class PostedMessage(_StrictModel):
    channel: str
    message_id: str
    posted_at: datetime

    @field_validator("posted_at")
    @classmethod
    def _posted_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)
