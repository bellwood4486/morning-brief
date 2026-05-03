from __future__ import annotations  # 型ヒントを文字列扱いにして前方参照を可能にする (PEP 563)

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


# 全ドメインモデルの共通制約のシングルソース。継承により全モデルに適用される。
class _StrictModel(BaseModel):
    # extra="forbid": 未知フィールドを拒否。
    # frozen=True: イミュータブル化で誤代入を ValidationError にできる。
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# 責務: datetime が tz-aware か検証する共通バリデータ。各モデルの field_validator から呼ぶ。
def _check_aware(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return v


class Email(_StrictModel):
    """1通の取り込み対象メール。"""

    id: str
    sender: str
    subject: str
    body_text: str
    body_html: str | None = None
    received_at: datetime
    links: list[str] = []

    # @classmethod とセットなのは Pydantic v2 の規約 (cls を受け、フィールド値を返す)
    @field_validator("received_at")
    @classmethod
    def _received_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)


class TldrItem(_StrictModel):
    """TL;DR ブロックの1項目。"""

    title_ja: str
    summary_ja: str
    source_url: str
    source_email_id: str


class DetailItem(_StrictModel):
    """詳細ブロックの1メール分。"""

    sender: str
    subject_ja: str
    points: list[str]
    glossary: dict[str, str] = {}
    source_url: str
    source_email_id: str


class Digest(_StrictModel):
    """1回の配信バッチで生成する要約全体。"""

    tldr_items: list[TldrItem]
    details: list[DetailItem]
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def _generated_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)


class ReactionFeedback(_StrictModel):
    """ダイジェストメッセージ全体に対する絵文字リアクション。"""

    # Literal は値そのものを型にする。enum より軽量で Pydantic と相性良い。
    kind: Literal["reaction"]
    message_id: str
    emoji: str
    user: str
    raw: dict[str, Any] = {}


class ThreadReplyFeedback(_StrictModel):
    """ダイジェストメッセージへのスレッド返信。"""

    kind: Literal["thread_reply"]
    message_id: str
    text: str
    user: str
    raw: dict[str, Any] = {}


# TypeAlias は Python 3.11+ の明示的型エイリアス宣言。呼び出し側で list[Feedback] を維持するため。
# Annotated + Field(discriminator="kind") で kind 値から具象型を Pydantic が振り分ける。
Feedback: TypeAlias = Annotated[
    ReactionFeedback | ThreadReplyFeedback,
    Field(discriminator="kind"),
]


class PostedMessage(_StrictModel):
    """Notifier が投稿したメッセージの識別情報。"""

    channel: str
    message_id: str
    posted_at: datetime

    @field_validator("posted_at")
    @classmethod
    def _posted_at_aware(cls, v: datetime) -> datetime:
        return _check_aware(v)
