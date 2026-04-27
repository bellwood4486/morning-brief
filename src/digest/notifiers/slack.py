from datetime import UTC, datetime
from typing import Any, cast

from slack_sdk import WebClient  # 設計境界: このファイル限定 (アーキテクチャテストで強制)

from digest.models import (
    Feedback,
    PostedMessage,
    ReactionFeedback,
    ThreadReplyFeedback,
)


# 責務: Slack Web API を介してダイジェストの投稿とフィードバック収集を行う Notifier 実装。
class SlackNotifier:
    # client は呼び出し側 (modal_app.py) で組み立てた WebClient を受け取る。
    # 依存注入にすることでテスト時のモック差し替えと Notifier Protocol の交換可能性が両立する。
    def __init__(self, client: WebClient, channel: str) -> None:
        self._client = client
        self._channel = channel

    def send(self, blocks: list[dict[str, Any]]) -> PostedMessage:
        response = self._client.chat_postMessage(channel=self._channel, blocks=blocks)
        # SlackResponse.__getitem__ は Any | None を返す。chat.postMessage 成功時は str である
        # という API 契約を cast で表明する。
        ts = cast(str, response["ts"])
        return PostedMessage(
            channel=self._channel,
            message_id=ts,
            # Slack の ts は Unix 秒 (float 文字列)。tz-aware UTC に変換して制約を満たす。
            posted_at=datetime.fromtimestamp(float(ts), tz=UTC),
        )

    def collect_feedback(self, message_id: str) -> list[Feedback]:
        feedbacks: list[Feedback] = []
        feedbacks.extend(self._collect_reactions(message_id))
        feedbacks.extend(self._collect_thread_replies(message_id))
        return feedbacks

    def _collect_reactions(self, message_id: str) -> list[Feedback]:
        response = self._client.reactions_get(
            channel=self._channel, timestamp=message_id, full=True
        )
        message = response.get("message") or {}
        reactions = message.get("reactions") or []
        result: list[Feedback] = []
        for reaction in reactions:
            name: str = reaction["name"]
            users: list[str] = reaction.get("users") or []
            for user in users:
                result.append(
                    ReactionFeedback(
                        kind="reaction",
                        message_id=message_id,
                        emoji=name,
                        user=user,
                        raw={"count": reaction.get("count", 0)},
                    )
                )
        return result

    def _collect_thread_replies(self, message_id: str) -> list[Feedback]:
        response = self._client.conversations_replies(channel=self._channel, ts=message_id)
        messages: list[dict[str, Any]] = response.get("messages") or []
        result: list[Feedback] = []
        for msg in messages:
            # 親メッセージ自身は ts == message_id なので除外し、返信のみを Feedback にする。
            if msg.get("ts") == message_id:
                continue
            result.append(
                ThreadReplyFeedback(
                    kind="thread_reply",
                    message_id=message_id,
                    text=msg.get("text", ""),
                    user=msg.get("user", ""),
                    raw={
                        "ts": msg.get("ts", ""),
                        "thread_ts": msg.get("thread_ts", ""),
                    },
                )
            )
        return result
