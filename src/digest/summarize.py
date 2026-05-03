from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from digest.models import DetailItem, Digest, Email, TldrItem


class _DigestContent(BaseModel):
    """Gemini が返す要約コンテンツ。generated_at は Python 側で付与するため除外。"""

    tldr_items: list[TldrItem]
    details: list[DetailItem]


def _system_prompt(ctx: RunContext[str]) -> str:
    return ctx.deps


# モジュールレベルで Agent を定義。テスト時は _agent.override() で差し替える。
# instrument=True: Logfire が設定済みの場合に全 LLM スパンを自動送信 (ADR-010/013)。
_agent: Agent[str, _DigestContent] = Agent(
    "google-gla:gemini-2.5-flash",
    output_type=_DigestContent,
    retries=2,
    deps_type=str,
    defer_model_check=True,
    instrument=True,
    instructions=_system_prompt,
)


@dataclass(frozen=True)
class GeminiClient:
    """Gemini で英語メール群を日本語ダイジェストに要約する。"""

    api_key: str
    model_name: str = field(default="gemini-2.5-flash")

    def summarize(
        self,
        emails: list[Email],
        prompt: str,
        model: str | None = None,
    ) -> Digest:
        """メール群を Gemini で日本語ダイジェストに変換する。

        prompt は seeds/summarize_prompt.md などを呼び出し側で読み込んで渡す。
        """
        google_model = GoogleModel(
            model or self.model_name,
            provider=GoogleProvider(api_key=self.api_key),
        )
        result = _agent.run_sync(
            _serialize_emails(emails),
            deps=prompt,
            model=google_model,
        )
        return Digest(
            tldr_items=result.output.tldr_items,
            details=result.output.details,
            generated_at=datetime.now(UTC),
        )


def build_gemini_client(api_key: str) -> GeminiClient:
    return GeminiClient(api_key=api_key)


def _serialize_emails(emails: list[Email]) -> str:
    return json.dumps(
        [
            {
                "id": e.id,
                "sender": e.sender,
                "subject": e.subject,
                "body_text": e.body_text,
                "links": e.links,
            }
            for e in emails
        ],
        ensure_ascii=False,
    )
