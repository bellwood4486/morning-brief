from __future__ import annotations

import base64
import html as html_lib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from google.oauth2.credentials import Credentials

# 設計境界: googleapiclient の import はこのファイル限定 (アーキテクチャテストで強制)
from googleapiclient.discovery import build

from digest.models import Email

_URL_RE = re.compile(r"https?://[^\s<>\"']+")


# dataclass: __init__ 等を自動生成するデコレータ。frozen=True でイミュータブル化する。
@dataclass(frozen=True)
class GmailClient:
    """Gmail API 経由でメール取得と処理済みラベル付与を行う。受信専用 (送信不可)。"""

    service: Any  # googleapiclient.discovery.build の返す Resource。型スタブ欠如のため Any
    processed_label_id: str

    def fetch_unread(self, label: str, since: timedelta) -> list[Email]:
        """指定ラベルが付いた since 以内のメールを一覧で返す。"""
        after_ts = int((datetime.now(UTC) - since).timestamp())
        q = f"label:{label} after:{after_ts}"
        response = cast(
            dict[str, Any],
            self.service.users().messages().list(userId="me", q=q).execute(),
        )
        messages = cast(list[dict[str, Any]], response.get("messages", []))
        emails: list[Email] = []
        for msg in messages:
            msg_id = cast(str, msg["id"])
            full_msg = cast(
                dict[str, Any],
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute(),
            )
            emails.append(_extract_email(full_msg))
        return emails

    # Iterable は list だけでなくジェネレータも受け取れる汎用型
    def mark_processed(self, emails: Iterable[Email]) -> None:
        """各メールに processed_label_id ラベルを付与する。"""
        for email in emails:
            self.service.users().messages().modify(
                userId="me",
                id=email.id,
                body={"addLabelIds": [self.processed_label_id]},
            ).execute()


def build_gmail_client(
    creds_json: str,
    processed_label_name: str = "Newsletter/Tech/Processed",
) -> GmailClient:
    """gmail_oauth.json の JSON 文字列からサービスを組み立て GmailClient を返す。"""
    # from_authorized_user_info: bootstrap_oauth.py の to_json() 出力を Credentials に再構築する
    # google-auth が from_authorized_user_info をアノテーションしていないため type: ignore
    creds = Credentials.from_authorized_user_info(  # type: ignore[no-untyped-call]
        json.loads(creds_json)
    )
    service = build("gmail", "v1", credentials=creds)
    processed_label_id = _resolve_label_id(service, processed_label_name)
    return GmailClient(service=service, processed_label_id=processed_label_id)


def _resolve_label_id(service: Any, name: str) -> str:
    response = cast(
        dict[str, Any],
        service.users().labels().list(userId="me").execute(),
    )
    labels = cast(list[dict[str, Any]], response.get("labels", []))
    for label in labels:
        if cast(str, label.get("name", "")) == name:
            return cast(str, label["id"])
    raise ValueError(f"Gmail ラベル '{name}' が見つかりません。Gmail で作成してください。")


def _extract_email(message: dict[str, Any]) -> Email:
    msg_id = cast(str, message["id"])
    received_at = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=UTC)

    headers = cast(list[dict[str, str]], message.get("payload", {}).get("headers", []))
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

    payload = cast(dict[str, Any], message.get("payload", {}))
    text_body, html_body = _decode_parts(payload)

    if text_body is not None:
        body_text = text_body
    elif html_body is not None:
        body_text = _strip_html_tags(html_body)
    else:
        body_text = ""

    links = _extract_links(body_text, html_body)
    return Email(
        id=msg_id,
        sender=sender,
        subject=subject,
        body_text=body_text,
        body_html=html_body,
        received_at=received_at,
        links=links,
    )


def _decode_parts(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    mime_type = cast(str, payload.get("mimeType", ""))

    if mime_type == "text/plain":
        data = cast(str, payload.get("body", {}).get("data", ""))
        return (_b64decode(data) if data else None), None

    if mime_type == "text/html":
        data = cast(str, payload.get("body", {}).get("data", ""))
        return None, (_b64decode(data) if data else None)

    if mime_type.startswith("multipart/"):
        text_acc: str | None = None
        html_acc: str | None = None
        for part in cast(list[dict[str, Any]], payload.get("parts", [])):
            t, h = _decode_parts(part)
            if t is not None:
                text_acc = t
            if h is not None:
                html_acc = h
        return text_acc, html_acc

    return None, None


def _b64decode(data: str) -> str:
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _strip_html_tags(html_body: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_body)
    return html_lib.unescape(text).strip()


def _extract_links(text: str, html_body: str | None) -> list[str]:
    combined = text + ("\n" + html_body if html_body else "")
    return list(dict.fromkeys(_URL_RE.findall(combined)))
