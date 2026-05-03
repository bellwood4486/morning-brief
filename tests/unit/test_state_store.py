from __future__ import annotations

from pathlib import Path

from digest.models import ReactionFeedback, ThreadReplyFeedback
from digest.state_store import StateStore


def _make_reaction(emoji: str = "thumbsup", message_id: str = "ts-001") -> ReactionFeedback:
    return ReactionFeedback(
        kind="reaction",
        message_id=message_id,
        emoji=emoji,
        user="U001",
    )


def _make_reply(text: str = "good post", message_id: str = "ts-001") -> ThreadReplyFeedback:
    return ThreadReplyFeedback(
        kind="thread_reply",
        message_id=message_id,
        text=text,
        user="U002",
    )


class TestGetLastMessageId:
    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        assert store.get_last_message_id() is None

    def test_returns_saved_message_id(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.set_last_message_id("1234567890.123456")
        assert store.get_last_message_id() == "1234567890.123456"


class TestSetLastMessageId:
    def test_creates_parent_dirs_automatically(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "deep" / "dir")
        store.set_last_message_id("ts-001")
        assert store.get_last_message_id() == "ts-001"

    def test_overwrites_existing_value(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.set_last_message_id("ts-001")
        store.set_last_message_id("ts-002")
        assert store.get_last_message_id() == "ts-002"

    def test_no_tmp_file_left_after_write(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.set_last_message_id("ts-001")
        tmp_files = list((tmp_path / "state").glob("*.tmp"))
        assert tmp_files == []


class TestAppendFeedback:
    def test_empty_list_does_not_create_file(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.append_feedback([])
        assert not store.feedback_path.exists()

    def test_creates_jsonl_file(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.append_feedback([_make_reaction()])
        assert store.feedback_path.exists()

    def test_appends_on_multiple_calls(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.append_feedback([_make_reaction("thumbsup")])
        store.append_feedback([_make_reply("interesting")])
        loaded = store.load_feedbacks()
        assert len(loaded) == 2

    def test_each_line_is_valid_json(self, tmp_path: Path) -> None:
        import json

        store = StateStore(tmp_path)
        store.append_feedback([_make_reaction()])
        lines = store.feedback_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["kind"] == "reaction"

    def test_creates_base_dir_if_missing(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "nonexistent")
        store.append_feedback([_make_reaction()])
        assert store.feedback_path.exists()


class TestLoadFeedbacks:
    def test_returns_empty_list_when_file_missing(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        assert store.load_feedbacks() == []

    def test_round_trip_reaction_feedback(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        original = _make_reaction("thumbsup", "ts-001")
        store.append_feedback([original])
        loaded = store.load_feedbacks()
        assert len(loaded) == 1
        item = loaded[0]
        assert isinstance(item, ReactionFeedback)
        assert item.emoji == "thumbsup"
        assert item.message_id == "ts-001"

    def test_round_trip_thread_reply_feedback(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        original = _make_reply("great article")
        store.append_feedback([original])
        loaded = store.load_feedbacks()
        assert len(loaded) == 1
        item = loaded[0]
        assert isinstance(item, ThreadReplyFeedback)
        assert item.text == "great article"

    def test_round_trip_mixed_feedback(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path)
        store.append_feedback([_make_reaction(), _make_reply()])
        loaded = store.load_feedbacks()
        assert len(loaded) == 2
        kinds = {fb.kind for fb in loaded}
        assert kinds == {"reaction", "thread_reply"}
