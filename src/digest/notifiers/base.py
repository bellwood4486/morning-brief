from typing import Any, Protocol

from digest.models import Feedback, PostedMessage


class Notifier(Protocol):
    """Protocol for notification backends."""

    def send(self, blocks: list[dict[str, Any]]) -> PostedMessage: ...

    def collect_feedback(self, message_id: str) -> list[Feedback]: ...
