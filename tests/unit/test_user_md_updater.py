from __future__ import annotations

from pathlib import Path

from pydantic_ai.models.test import TestModel

from digest.models import ReactionFeedback
from digest.state_store import StateStore
from digest.user_md_updater import UserMdDiff, UserMdUpdater, _diff_agent
from digest.userdoc_store import UserdocStore


def _make_userdoc_store(tmp_path: Path, user_md: str = "# USER.md\n\n初期版。\n") -> UserdocStore:
    vol = tmp_path / "vol"
    vol.mkdir(parents=True, exist_ok=True)
    (vol / "USER.md").write_text(user_md, encoding="utf-8")
    (vol / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    return UserdocStore(vol)


def _populate_feedback(store: StateStore, n: int) -> None:
    feedbacks = [
        ReactionFeedback(kind="reaction", message_id=f"ts-{i}", emoji="thumbsup", user=f"U{i:03}")
        for i in range(n)
    ]
    store.append_feedback(feedbacks)


def _diff_output(summary: str = "テスト更新") -> dict[str, object]:
    return {
        "user_md_content": "# USER.md\n\n更新後。\n",
        "memory_md_content": "# Memory Index\n",
        "change_summary": summary,
    }


class TestUpdateIfReadyBelowThreshold:
    def test_returns_none_when_no_feedback(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert result is None

    def test_returns_none_below_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        _populate_feedback(store, 3)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert result is None

    def test_lm_not_called_below_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        _populate_feedback(store, 2)
        updater = UserMdUpdater(api_key="test")
        call_count = 0

        class CountingModel(TestModel):
            def request(self, *args: object, **kwargs: object) -> object:
                nonlocal call_count
                call_count += 1
                return super().request(*args, **kwargs)  # type: ignore[return-value]

        with _diff_agent.override(model=CountingModel(custom_output_args=_diff_output())):
            updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert call_count == 0


class TestUpdateIfReadyGeneratesDiff:
    def test_returns_userdoc_diff_at_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert isinstance(result, UserMdDiff)
        assert result.user_md_content == "# USER.md\n\n更新後。\n"

    def test_returns_userdoc_diff_above_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        _populate_feedback(store, 10)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output("多め更新"))):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert isinstance(result, UserMdDiff)
        assert result.change_summary == "多め更新"

    def test_no_side_effects_on_volume(self, tmp_path: Path) -> None:
        """update_if_ready は副作用なしの純粋関数であることを確認する。"""
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path, user_md="# USER.md\n\n初期版。\n")
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        # Volume の USER.md が書き換えられていないこと
        current_user, _ = userdoc_store.read()
        assert current_user == "# USER.md\n\n初期版。\n"
        # feedback.jsonl が rotate されていないこと
        assert store.feedback_path.exists()

    def test_memory_md_optional(self, tmp_path: Path) -> None:
        """MEMORY.md が Volume に存在しなくても例外を出さない。"""
        store = StateStore(tmp_path / "state")
        vol = tmp_path / "vol"
        vol.mkdir()
        (vol / "USER.md").write_text("# USER.md\n", encoding="utf-8")
        # MEMORY.md は作成しない
        userdoc_store = UserdocStore(vol)
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert isinstance(result, UserMdDiff)

    def test_change_summary_is_propagated(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        userdoc_store = _make_userdoc_store(tmp_path)
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        expected_summary = "Rust への強い関心が検出された"
        with _diff_agent.override(
            model=TestModel(custom_output_args=_diff_output(expected_summary))
        ):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                userdoc_store=userdoc_store,
                threshold=5,
            )
        assert result is not None
        assert result.change_summary == expected_summary
