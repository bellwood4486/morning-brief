from unittest.mock import MagicMock, patch

import pytest
from bootstrap_oauth import register_modal_secret


def test_register_calls_subprocess_with_correct_args() -> None:
    payload = '{"refresh_token": "token123"}'
    with patch("bootstrap_oauth.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        register_modal_secret("gmail-oauth", payload)
    mock_run.assert_called_once_with(
        [
            "uv",
            "run",
            "modal",
            "secret",
            "create",
            "--force",
            "gmail-oauth",
            f"GMAIL_OAUTH_JSON={payload}",
        ],
        check=False,
    )


def test_register_raises_on_nonzero_returncode(capsys: pytest.CaptureFixture[str]) -> None:
    payload = '{"refresh_token": "secret"}'
    with patch("bootstrap_oauth.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(SystemExit):
            register_modal_secret("gmail-oauth", payload)
    assert "自動登録に失敗しました" in capsys.readouterr().err


def test_register_does_not_print_payload_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    payload = '{"refresh_token": "supersecret"}'
    with patch("bootstrap_oauth.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        register_modal_secret("gmail-oauth", payload)
    assert payload not in capsys.readouterr().out
