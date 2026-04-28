from __future__ import annotations

import json
from pathlib import Path

import pytest

from digest.hermes_bridge import HermesBridge
from digest.models import (
    ReactionFeedback,
)

# tmp_path: pytest 組込み、テストごとに使い捨ての一時ディレクトリ Path を渡してくれる


def test_get_returns_none_when_no_state_file(tmp_path: Path) -> None:
    bridge = HermesBridge(state_dir=tmp_path)
    assert bridge.get_last_message_id() is None


def test_set_then_get_returns_value(tmp_path: Path) -> None:
    bridge = HermesBridge(state_dir=tmp_path)
    bridge.set_last_message_id("ts123")
    assert bridge.get_last_message_id() == "ts123"


def test_persistence_across_instances(tmp_path: Path) -> None:
    HermesBridge(state_dir=tmp_path).set_last_message_id("ts123")
    assert HermesBridge(state_dir=tmp_path).get_last_message_id() == "ts123"


def test_set_creates_parent_directory(tmp_path: Path) -> None:
    state_dir = tmp_path / "hermes"
    HermesBridge(state_dir=state_dir).set_last_message_id("ts123")
    assert (state_dir / "state" / "last_digest.json").exists()


def test_set_overwrites_previous_value(tmp_path: Path) -> None:
    bridge = HermesBridge(state_dir=tmp_path)
    bridge.set_last_message_id("ts100")
    bridge.set_last_message_id("ts200")
    assert bridge.get_last_message_id() == "ts200"


def test_get_returns_none_when_key_missing(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "last_digest.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({}), encoding="utf-8")
    assert HermesBridge(state_dir=tmp_path).get_last_message_id() is None


def test_set_is_atomic_no_tmp_file_left(tmp_path: Path) -> None:
    HermesBridge(state_dir=tmp_path).set_last_message_id("ts123")
    assert not (tmp_path / "state" / "last_digest.json.tmp").exists()


def test_set_is_idempotent_for_same_value(tmp_path: Path) -> None:
    bridge = HermesBridge(state_dir=tmp_path)
    state_file = tmp_path / "state" / "last_digest.json"
    bridge.set_last_message_id("ts123")
    first = state_file.read_text(encoding="utf-8")
    bridge.set_last_message_id("ts123")
    second = state_file.read_text(encoding="utf-8")
    assert first == second


def test_inject_feedback_logs_count(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    feedbacks = [
        ReactionFeedback(kind="reaction", message_id="ts123", emoji="thumbsup", user="U001"),
        ReactionFeedback(kind="reaction", message_id="ts123", emoji="thumbsdown", user="U002"),
    ]
    with caplog.at_level("INFO", logger="digest.hermes_bridge"):
        HermesBridge(state_dir=tmp_path).inject_feedback(feedbacks)
    assert "count=2" in caplog.text


def test_inject_feedback_with_empty_list(tmp_path: Path) -> None:
    HermesBridge(state_dir=tmp_path).inject_feedback([])


def test_observe_session_logs_keys(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    session_log = {"duration_sec": 42, "phase": "all"}
    with caplog.at_level("INFO", logger="digest.hermes_bridge"):
        HermesBridge(state_dir=tmp_path).observe_session(session_log)
    assert "duration_sec" in caplog.text
    assert "phase" in caplog.text
