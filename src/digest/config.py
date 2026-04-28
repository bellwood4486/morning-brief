from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


# domain の _StrictModel と別定義にして相互依存を避ける。
class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GmailConfig(_ConfigModel):
    label: str
    processed_label: str
    lookback_hours: int


class SlackConfig(_ConfigModel):
    digest_channel: str
    alerts_channel: str


class LlmConfig(_ConfigModel):
    model: str


class ScheduleConfig(_ConfigModel):
    cron: str


class Config(_ConfigModel):
    gmail: GmailConfig
    slack: SlackConfig
    llm: LlmConfig
    schedule: ScheduleConfig

    @classmethod
    def load(cls, path: Path) -> Config:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)
