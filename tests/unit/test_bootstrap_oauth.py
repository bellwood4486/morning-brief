import shlex

from bootstrap_oauth import build_modal_secret_command


def test_standard_input() -> None:
    result = build_modal_secret_command(
        "gmail-oauth",
        "GMAIL_OAUTH_JSON",
        '{"refresh_token": "token123"}',
    )
    expected = "modal secret create gmail-oauth GMAIL_OAUTH_JSON=" + shlex.quote(
        '{"refresh_token": "token123"}'
    )
    assert result == expected


def test_payload_roundtrip_with_special_chars() -> None:
    # シングルクォート・ドルサイン・バックスラッシュを含む payload でも
    # shlex.split でラウンドトリップが成立する (shell injection にならない)
    payload = """{"key": "it's $HOME \\"escaped\\""}"""
    result = build_modal_secret_command("gmail-oauth", "GMAIL_OAUTH_JSON", payload)
    parts = shlex.split(result)
    key, value = parts[-1].split("=", 1)
    assert key == "GMAIL_OAUTH_JSON"
    assert value == payload


def test_secret_name_with_shell_metachar() -> None:
    # secret_name にシェルメタ文字が混じっても shlex.quote でエスケープされる
    result = build_modal_secret_command("evil; rm -rf /", "GMAIL_OAUTH_JSON", "{}")
    parts = shlex.split(result)
    assert parts[3] == "evil; rm -rf /"
