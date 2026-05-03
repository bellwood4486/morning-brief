from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from digest.models import ReactionFeedback, ThreadReplyFeedback
from digest.seeds import load_seed
from digest.state_store import load_feedbacks_from_path

logger = logging.getLogger(__name__)

_FEEDBACK_THRESHOLD_DEFAULT = 5


class UserMdDiff(BaseModel):
    """Gemini が提案する seeds/ の更新内容。"""

    user_md_content: str
    memory_md_content: str
    change_summary: str


def _system_prompt(ctx: RunContext[str]) -> str:
    return ctx.deps


# モジュールレベルで Agent を定義。テスト時は _diff_agent.override() で差し替える。
_diff_agent: Agent[str, UserMdDiff] = Agent(
    "google-gla:gemini-2.5-flash",
    output_type=UserMdDiff,
    retries=2,
    deps_type=str,
    defer_model_check=True,
    instrument=True,
    instructions=_system_prompt,
)


@dataclass(frozen=True)
class UserMdUpdater:
    """フィードバックを解釈して USER.md / MEMORY.md の更新差分を Gemini で生成する。"""

    api_key: str
    model_name: str = field(default="gemini-2.5-flash")

    def update_if_ready(
        self,
        feedback_log_path: Path,
        seeds_dir: Path,
        threshold: int = _FEEDBACK_THRESHOLD_DEFAULT,
        dry_run: bool = False,
    ) -> bool:
        """フィードバック数が閾値以上なら Gemini で USER.md diff を生成する。

        Returns True if diff was generated, False if threshold not met.
        """
        feedbacks = load_feedbacks_from_path(feedback_log_path)
        if len(feedbacks) < threshold:
            logger.info(
                "Phase 5: feedback %d/%d, skip USER.md update",
                len(feedbacks),
                threshold,
            )
            return False

        user_md_path = seeds_dir / "USER.md"
        if not user_md_path.exists():
            logger.warning("Phase 5: USER.md not found in %s, skip update", seeds_dir)
            return False

        user_md = user_md_path.read_text(encoding="utf-8")
        memory_md_path = seeds_dir / "MEMORY.md"
        memory_md = memory_md_path.read_text(encoding="utf-8") if memory_md_path.exists() else ""

        prompt = load_seed("user_md_update_prompt.md")
        user_message = _build_user_message(feedbacks, user_md, memory_md)

        google_model = GoogleModel(
            self.model_name,
            provider=GoogleProvider(api_key=self.api_key),
        )
        result = _diff_agent.run_sync(user_message, deps=prompt, model=google_model)
        diff = result.output

        if dry_run:
            logger.info(
                "Phase 5: [dry_run] USER.md diff generated — %s",
                diff.change_summary,
            )
        else:
            logger.info(
                "Phase 5: USER.md diff generated — %s (T2.5 will create PR)",
                diff.change_summary,
            )
        return True


def build_user_md_updater(api_key: str, model_name: str = "gemini-2.5-flash") -> UserMdUpdater:
    return UserMdUpdater(api_key=api_key, model_name=model_name)


def _build_user_message(
    feedbacks: list[ReactionFeedback | ThreadReplyFeedback],
    user_md: str,
    memory_md: str,
) -> str:
    feedback_lines = "\n".join(fb.model_dump_json() for fb in feedbacks)
    mem_section = memory_md if memory_md.strip() else "(空)"
    return (
        "## フィードバックログ\n\n"
        + feedback_lines
        + "\n\n## 現在の USER.md\n\n"
        + user_md
        + "\n\n## 現在の MEMORY.md\n\n"
        + mem_section
    )
