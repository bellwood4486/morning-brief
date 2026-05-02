from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# 設計境界: google.genai の import はこのファイル限定 (アーキテクチャテストで強制予定)
from google import genai
from google.genai import types as genai_types

from digest.models import Digest, Email
from digest.observability import trace_llm


@dataclass(frozen=True)
class GeminiClient:
    """Gemini で英語メール群を日本語ダイジェストに要約する。"""

    client: Any  # google.genai.Client。gmail_client と同じく Any で統一

    @trace_llm("gemini.summarize")
    def summarize(
        self,
        emails: list[Email],
        prompt: str,
        model: str = "gemini-2.5-flash",
    ) -> Digest:
        """メール群を Gemini で日本語ダイジェストに変換する。

        prompt は seeds/summarize_prompt.md などを呼び出し側で読み込んで渡す。
        """
        serialized = _serialize_emails(emails)
        response = self.client.models.generate_content(
            model=model,
            contents=serialized,
            config=genai_types.GenerateContentConfig(
                system_instruction=prompt,
                response_mime_type="application/json",
            ),
        )
        text = response.text
        if text is None:
            raise RuntimeError("Gemini returned no text")
        return Digest.model_validate_json(text)


def build_gemini_client(api_key: str) -> GeminiClient:
    return GeminiClient(client=genai.Client(api_key=api_key))


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
