from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from digest.models import Feedback, ReactionFeedback, ThreadReplyFeedback

logger = logging.getLogger(__name__)

# Feedback の discriminated union を JSON から復元するためのアダプタ。
_feedback_adapter: TypeAdapter[ReactionFeedback | ThreadReplyFeedback] = TypeAdapter(Feedback)


def load_feedbacks_from_path(
    path: Path,
) -> list[ReactionFeedback | ThreadReplyFeedback]:
    """JSONL ファイルからフィードバック一覧を読み込む。ファイル不在時は空リストを返す。"""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_feedback_adapter.validate_json(line) for line in lines if line.strip()]


class StateStore:
    """Modal Volume 上の永続状態 (last_digest.json / feedback.jsonl) を管理する。"""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    @property
    def feedback_path(self) -> Path:
        return self._base_dir / "feedback.jsonl"

    def get_last_message_id(self) -> str | None:
        """前日ダイジェストの Slack メッセージ ID を返す。ファイル不在時は None。"""
        path = self._base_dir / "state" / "last_digest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data["message_id"])

    def set_last_message_id(self, message_id: str) -> None:
        """Slack メッセージ ID を原子的に書き込む (一時ファイル + os.replace)。"""
        state_dir = self._base_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        dest = state_dir / "last_digest.json"
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps({"message_id": message_id}), encoding="utf-8")
        tmp.replace(dest)

    def append_feedback(self, feedbacks: list[Feedback]) -> None:
        """feedback.jsonl にフィードバックを追記する。空リスト時は no-op。"""
        if not feedbacks:
            return
        self._base_dir.mkdir(parents=True, exist_ok=True)
        with self.feedback_path.open("a", encoding="utf-8") as f:
            for fb in feedbacks:
                f.write(fb.model_dump_json() + "\n")

    def load_feedbacks(self) -> list[ReactionFeedback | ThreadReplyFeedback]:
        """feedback.jsonl に蓄積されたフィードバックを全件返す。"""
        return load_feedbacks_from_path(self.feedback_path)

    def rotate_feedback(self, suffix: str = "") -> Path | None:
        """feedback.jsonl を archived 名に原子的にリネームする。

        archived 名: feedback.jsonl.archived.<UTC ISO8601 basic>[.suffix]
        元ファイルが存在しなければ None を返す。
        """
        src = self.feedback_path
        if not src.exists():
            return None
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        suffix_part = f".{suffix}" if suffix else ""
        dest = src.with_name(f"{src.name}.archived.{timestamp}{suffix_part}")
        src.replace(dest)
        return dest


def build_state_store(base_dir: Path) -> StateStore:
    return StateStore(base_dir)
