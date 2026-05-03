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
from digest.userdoc_store import UserdocStore

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
        userdoc_store: UserdocStore,
        threshold: int = _FEEDBACK_THRESHOLD_DEFAULT,
    ) -> UserMdDiff | None:
        """フィードバック数が閾値以上なら Gemini で USER.md / MEMORY.md diff を生成する。

        Returns UserMdDiff if diff was generated, None if threshold not met.
        副作用なし — Volume への書き込みは呼び出し側 (modal_app.py) の責務。
        """
        feedbacks = load_feedbacks_from_path(feedback_log_path)
        if len(feedbacks) < threshold:
            logger.info(
                "Phase 5: feedback %d/%d, skip USER.md update",
                len(feedbacks),
                threshold,
            )
            return None

        user_md, memory_md = userdoc_store.read()

        prompt = load_seed("user_md_update_prompt.md")
        user_message = _build_user_message(feedbacks, user_md, memory_md)

        google_model = GoogleModel(
            self.model_name,
            provider=GoogleProvider(api_key=self.api_key),
        )
        result = _diff_agent.run_sync(user_message, deps=prompt, model=google_model)
        diff = result.output

        logger.info("Phase 5: USER.md diff generated — %s", diff.change_summary)
        return diff


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
