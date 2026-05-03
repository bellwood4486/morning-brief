from __future__ import annotations

from pathlib import Path

from pydantic_ai.models.test import TestModel

from digest.models import ReactionFeedback
from digest.state_store import StateStore
from digest.user_md_updater import UserMdUpdater, _diff_agent


def _seed_dir(tmp_path: Path, user_md: str = "# USER.md\n\n初期版。\n") -> Path:
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "USER.md").write_text(user_md, encoding="utf-8")
    return seeds


def _populate_feedback(store: StateStore, n: int) -> None:
    feedbacks = [
        ReactionFeedback(kind="reaction", message_id=f"ts-{i}", emoji="thumbsup", user=f"U{i:03}")
        for i in range(n)
    ]
    store.append_feedback(feedbacks)


def _diff_output(summary: str = "テスト更新") -> dict[str, object]:
    return {
        "user_md_content": "# USER.md\n\n更新後。\n",
        "memory_md_content": "",
        "change_summary": summary,
    }


class TestUpdateIfReadyBelowThreshold:
    def test_returns_false_when_no_feedback(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is False

    def test_returns_false_below_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path)
        _populate_feedback(store, 3)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is False


class TestUpdateIfReadyGeneratesDiff:
    def test_returns_true_at_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path)
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is True

    def test_returns_true_above_threshold(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path)
        _populate_feedback(store, 10)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is True

    def test_returns_false_when_user_md_missing(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is False

    def test_dry_run_does_not_write_side_effects(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path, user_md="# USER.md\n\n初期版。\n")
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output("dry run 更新"))):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
                dry_run=True,
            )
        assert result is True
        # dry_run=True でも seeds/USER.md は書き換えない (T2.5 が PR 作成を担う)
        assert (seeds / "USER.md").read_text(encoding="utf-8") == "# USER.md\n\n初期版。\n"

    def test_memory_md_optional(self, tmp_path: Path) -> None:
        store = StateStore(tmp_path / "state")
        seeds = _seed_dir(tmp_path)
        _populate_feedback(store, 5)
        updater = UserMdUpdater(api_key="test")
        # MEMORY.md が存在しなくても例外を出さない
        with _diff_agent.override(model=TestModel(custom_output_args=_diff_output())):
            result = updater.update_if_ready(
                feedback_log_path=store.feedback_path,
                seeds_dir=seeds,
                threshold=5,
            )
        assert result is True
