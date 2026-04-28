from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# 設計境界: google.genai の import はこのファイル限定 (アーキテクチャテストで強制予定)
from google import genai
from google.genai import types as genai_types

from digest.models import Digest, Email


@dataclass(frozen=True)
class GeminiClient:
    """Gemini API クライアントの薄い wrapper。テスト時に差し替え可能。"""

    client: Any  # google.genai.Client。gmail_client と同じく Any で統一


def build_gemini_client(api_key: str) -> GeminiClient:
    return GeminiClient(client=genai.Client(api_key=api_key))


def summarize(
    emails: list[Email],
    prompt: str,
    client: GeminiClient,
    model: str = "gemini-2.5-flash",
) -> Digest:
    """メール群を Gemini で日本語ダイジェストに変換する。

    prompt は seeds/summarize_prompt.md などを呼び出し側で読み込んで渡す。
    response_schema による型付きパースは SDK/seed が安定したら検討。
    """
    serialized = _serialize_emails(emails)
    response = client.client.models.generate_content(
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
