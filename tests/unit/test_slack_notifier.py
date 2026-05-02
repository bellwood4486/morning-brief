from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from pydantic import ValidationError

# mocker は pytest-mock が提供する fixture。teardown を自動処理してくれる。
from pytest_mock import MockerFixture
from slack_sdk import WebClient

from digest.models import ReactionFeedback, ThreadReplyFeedback
from digest.notifiers.slack import SlackNotifier, build_slack_notifier


# 責務: デフォルト構成の SlackNotifier とモック化された WebClient を返すファクトリ。
def _make_notifier(
    mocker: MockerFixture, *, channel: str = "#newsletter-digest"
) -> tuple[SlackNotifier, Mock]:
    client = mocker.Mock(spec=WebClient)
    return SlackNotifier(client=client, channel=channel), client


def _slack_response(data: dict[str, Any]) -> MagicMock:
    # SlackResponse は dict 風オブジェクト。必要なメソッドだけ MagicMock で擬似する。
    resp = MagicMock()
    resp.__getitem__.side_effect = lambda k: data[k]
    resp.get.side_effect = lambda k, default=None: data.get(k, default)
    return resp


_TS = "1700000000.000100"


# --- send ---


def test_send_calls_chat_postmessage_with_channel_and_blocks(
    mocker: MockerFixture,
) -> None:
    notifier, client = _make_notifier(mocker)
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hello"}}]
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})

    notifier.send(blocks, text="hello")

    client.chat_postMessage.assert_called_once_with(
        channel="#newsletter-digest", blocks=blocks, text="hello"
    )


def test_send_passes_text_to_chat_postmessage(mocker: MockerFixture) -> None:
    # 仕様: 呼び出し側が指定した fallback text は変更されず Slack API に転送される。
    notifier, client = _make_notifier(mocker)
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})
    notification_text = "Tech Newsletter Digest 2026-05-02 (JST) — TL;DR 3 件"

    notifier.send([], text=notification_text)

    _, kwargs = client.chat_postMessage.call_args
    assert kwargs["text"] == notification_text


def test_send_returns_posted_message_with_ts_as_message_id(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})

    result = notifier.send([], text="dummy")

    assert result.message_id == _TS


def test_send_posted_at_is_aware_utc_from_ts(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})

    result = notifier.send([], text="dummy")

    expected = datetime.fromtimestamp(float(_TS), tz=UTC)
    assert result.posted_at == expected
    assert result.posted_at.tzinfo is UTC


def test_send_posted_message_channel_matches_constructor(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker, channel="#custom-channel")
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})

    result = notifier.send([], text="dummy")

    assert result.channel == "#custom-channel"


def test_send_blocks_passed_through_unchanged(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    blocks = [{"type": "header"}, {"type": "section"}]
    client.chat_postMessage.return_value = _slack_response({"ts": _TS})

    notifier.send(blocks, text="dummy")

    _, kwargs = client.chat_postMessage.call_args
    assert kwargs["blocks"] == blocks


# --- collect_feedback (reactions) ---


def test_collect_feedback_calls_slack_apis_with_correct_args(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"message": {}})
    client.conversations_replies.return_value = _slack_response({"messages": []})

    notifier.collect_feedback("ts123")

    client.reactions_get.assert_called_once_with(
        channel="#newsletter-digest", timestamp="ts123", full=True
    )
    client.conversations_replies.assert_called_once_with(channel="#newsletter-digest", ts="ts123")


def test_collect_feedback_returns_reaction_feedback_per_user(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response(
        {"message": {"reactions": [{"name": "thumbsup", "count": 2, "users": ["U1", "U2"]}]}}
    )
    client.conversations_replies.return_value = _slack_response({"messages": []})

    feedbacks = notifier.collect_feedback("ts123")

    reactions = [f for f in feedbacks if isinstance(f, ReactionFeedback)]
    assert len(reactions) == 2
    assert all(f.emoji == "thumbsup" for f in reactions)
    assert {f.user for f in reactions} == {"U1", "U2"}
    assert all(f.message_id == "ts123" for f in reactions)


def test_collect_feedback_handles_empty_reactions(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"message": {}})
    client.conversations_replies.return_value = _slack_response({"messages": []})

    feedbacks = notifier.collect_feedback("ts123")

    assert not any(isinstance(f, ReactionFeedback) for f in feedbacks)


def test_collect_feedback_handles_no_message_field(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"ok": True})
    client.conversations_replies.return_value = _slack_response({"messages": []})

    feedbacks = notifier.collect_feedback("ts123")

    assert not any(isinstance(f, ReactionFeedback) for f in feedbacks)


# --- collect_feedback (thread_replies) ---


def test_collect_feedback_extracts_thread_replies_excluding_parent(
    mocker: MockerFixture,
) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"message": {}})
    client.conversations_replies.return_value = _slack_response(
        {
            "messages": [
                {"ts": "ts123", "text": "親メッセージ", "user": "bot"},
                {"ts": "ts124", "text": "返信1", "user": "U1", "thread_ts": "ts123"},
                {"ts": "ts125", "text": "返信2", "user": "U2", "thread_ts": "ts123"},
            ]
        }
    )

    feedbacks = notifier.collect_feedback("ts123")

    replies = [f for f in feedbacks if isinstance(f, ThreadReplyFeedback)]
    assert len(replies) == 2
    assert replies[0].text == "返信1"
    assert replies[0].user == "U1"
    assert replies[0].message_id == "ts123"
    assert replies[1].text == "返信2"


def test_collect_feedback_parent_excluded_by_ts_equality(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"message": {}})
    client.conversations_replies.return_value = _slack_response(
        {"messages": [{"ts": "ts123", "text": "親", "user": "bot"}]}
    )

    feedbacks = notifier.collect_feedback("ts123")

    assert not any(isinstance(f, ThreadReplyFeedback) for f in feedbacks)


def test_collect_feedback_handles_no_thread_replies(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response({"message": {}})
    client.conversations_replies.return_value = _slack_response({"messages": []})

    feedbacks = notifier.collect_feedback("ts123")

    assert not any(isinstance(f, ThreadReplyFeedback) for f in feedbacks)


# --- collect_feedback (combined) ---


def test_collect_feedback_returns_reactions_and_replies_combined(
    mocker: MockerFixture,
) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response(
        {"message": {"reactions": [{"name": "+1", "count": 1, "users": ["U1"]}]}}
    )
    client.conversations_replies.return_value = _slack_response(
        {
            "messages": [
                {"ts": "ts123", "text": "親", "user": "bot"},
                {"ts": "ts124", "text": "コメントです", "user": "U2", "thread_ts": "ts123"},
            ]
        }
    )

    feedbacks = notifier.collect_feedback("ts123")

    assert len(feedbacks) == 2
    assert any(isinstance(f, ReactionFeedback) for f in feedbacks)
    assert any(isinstance(f, ThreadReplyFeedback) for f in feedbacks)


def test_collect_feedback_message_id_propagated_to_all(mocker: MockerFixture) -> None:
    notifier, client = _make_notifier(mocker)
    client.reactions_get.return_value = _slack_response(
        {"message": {"reactions": [{"name": "+1", "count": 1, "users": ["U1"]}]}}
    )
    client.conversations_replies.return_value = _slack_response(
        {
            "messages": [
                {"ts": "ts123", "text": "親", "user": "bot"},
                {"ts": "ts124", "text": "返信", "user": "U2", "thread_ts": "ts123"},
            ]
        }
    )

    feedbacks = notifier.collect_feedback("ts123")

    assert all(f.message_id == "ts123" for f in feedbacks)


# --- build_slack_notifier ---


def test_build_slack_notifier_returns_slack_notifier() -> None:
    notifier = build_slack_notifier(token="xoxb-fake", channel="#test")
    assert isinstance(notifier, SlackNotifier)


def test_build_slack_notifier_channel_is_set() -> None:
    notifier = build_slack_notifier(token="xoxb-fake", channel="#my-channel")
    assert notifier._channel == "#my-channel"


# ---


@pytest.mark.parametrize("invalid_attr", ["emoji", "user", "message_id"])
def test_reaction_feedback_required_fields(invalid_attr: str) -> None:
    valid: dict[str, Any] = {
        "kind": "reaction",
        "message_id": "ts123",
        "emoji": "thumbsup",
        "user": "U1",
    }
    del valid[invalid_attr]
    with pytest.raises(ValidationError):
        ReactionFeedback(**valid)  # type: ignore[arg-type]
