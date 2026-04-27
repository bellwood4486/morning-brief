import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from digest.gmail_client import GmailClient, build_gmail_client


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _message(
    msg_id: str,
    *,
    subject: str,
    sender: str,
    internal_ms: int,
    text: str | None = None,
    html: str | None = None,
) -> dict[str, Any]:
    headers = [
        {"name": "From", "value": sender},
        {"name": "Subject", "value": subject},
    ]
    parts: list[dict[str, Any]] = []
    if text is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(text)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    payload: dict[str, Any] = {
        "mimeType": "multipart/alternative",
        "headers": headers,
        "parts": parts,
    }
    return {
        "id": msg_id,
        "internalDate": str(internal_ms),
        "payload": payload,
    }


def _make_client(
    mocker: Any, *, label_id: str = "LABEL_PROCESSED"
) -> tuple[GmailClient, MagicMock]:
    service = mocker.MagicMock()
    return GmailClient(service=service, processed_label_id=label_id), service


def test_fetch_unread_returns_emails_within_24h(mocker: Any) -> None:
    client, service = _make_client(mocker)
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    msgs = [
        _message(
            "m1", subject="S1", sender="a@x.com", internal_ms=now_ms - 3_600_000, text="hello"
        ),
        _message(
            "m2", subject="S2", sender="b@x.com", internal_ms=now_ms - 7_200_000, text="world"
        ),
        _message(
            "m3", subject="S3", sender="c@x.com", internal_ms=now_ms - 10_800_000, text="test"
        ),
    ]
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.side_effect = msgs

    result = client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    assert len(result) == 3


def test_fetch_unread_query_includes_label_and_after_timestamp(mocker: Any) -> None:
    client, service = _make_client(mocker)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": []
    }

    before_ts = int((datetime.now(UTC) - timedelta(hours=24)).timestamp())
    client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    after_ts = int((datetime.now(UTC) - timedelta(hours=24)).timestamp())

    call_kwargs = service.users.return_value.messages.return_value.list.call_args.kwargs
    q: str = call_kwargs["q"]
    assert "label:Newsletter/Tech" in q
    ts = int(q.split("after:")[-1])
    assert before_ts <= ts <= after_ts + 1  # 実行時差を最大 1 秒許容


def test_fetch_unread_handles_html_only_email(mocker: Any) -> None:
    client, service = _make_client(mocker)
    html_body = "<p>Hello <b>World</b></p>"
    msg = _message(
        "m1", subject="S", sender="a@x.com", internal_ms=1_748_000_000_000, html=html_body
    )
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = msg

    result = client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    email = result[0]
    assert email.body_html == html_body
    assert "<" not in email.body_text
    assert email.body_text != ""


def test_fetch_unread_handles_text_only_email(mocker: Any) -> None:
    client, service = _make_client(mocker)
    msg = _message(
        "m1", subject="S", sender="a@x.com", internal_ms=1_748_000_000_000, text="Hello World"
    )
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = msg

    result = client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    assert result[0].body_html is None
    assert result[0].body_text == "Hello World"


def test_fetch_unread_extracts_links_from_body(mocker: Any) -> None:
    client, service = _make_client(mocker)
    text = "Check https://example.com and https://foo.bar also https://example.com"
    msg = _message("m1", subject="S", sender="a@x.com", internal_ms=1_748_000_000_000, text=text)
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = msg

    result = client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    links = result[0].links
    assert "https://example.com" in links
    assert "https://foo.bar" in links
    assert len(links) == len(set(links))  # 重複なし


def test_fetch_unread_received_at_is_aware_utc(mocker: Any) -> None:
    client, service = _make_client(mocker)
    msg = _message("m1", subject="S", sender="a@x.com", internal_ms=1_748_000_000_000, text="hi")
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = msg

    result = client.fetch_unread("Newsletter/Tech", timedelta(hours=24))
    assert result[0].received_at.tzinfo is not None


def test_mark_processed_calls_modify_for_each_email(mocker: Any) -> None:
    client, service = _make_client(mocker, label_id="LABEL_PROCESSED")
    emails = [
        # frozen=True の Email は直接構築できる
        pytest.importorskip("digest.models").Email(
            id="m1",
            sender="a@x.com",
            subject="Sub1",
            body_text="t",
            received_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        pytest.importorskip("digest.models").Email(
            id="m2",
            sender="b@x.com",
            subject="Sub2",
            body_text="t",
            received_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
    ]
    client.mark_processed(emails)

    modify_mock = service.users.return_value.messages.return_value.modify
    assert modify_mock.call_count == 2
    ids_called = {c.kwargs["id"] for c in modify_mock.call_args_list}
    assert ids_called == {"m1", "m2"}
    for call in modify_mock.call_args_list:
        assert call.kwargs["body"] == {"addLabelIds": ["LABEL_PROCESSED"]}


def test_build_gmail_client_resolves_processed_label_id(mocker: Any) -> None:
    mocker.patch(
        "digest.gmail_client.Credentials.from_authorized_user_info",
        return_value=mocker.MagicMock(),
    )
    mock_service = mocker.MagicMock()
    mocker.patch("digest.gmail_client.build", return_value=mock_service)
    mock_service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [
            {"id": "LABEL_TECH", "name": "Newsletter/Tech"},
            {"id": "LABEL_PROC", "name": "Newsletter/Tech/Processed"},
        ]
    }

    client = build_gmail_client('{"key": "val"}')
    assert client.processed_label_id == "LABEL_PROC"
