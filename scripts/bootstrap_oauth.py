#!/usr/bin/env python
"""Gmail OAuth 認証情報を取得して Modal Secrets 登録コマンドを出力するローカル実行スクリプト。"""

import argparse
import logging
import os
import shlex
from pathlib import Path

# Desktop OAuth フロー: ブラウザを起動してリダイレクト URI をローカルサーバで受け取る
from google_auth_oauthlib.flow import InstalledAppFlow

# gmail.modify: メッセージ読み取り + ラベル付与 (Newsletter/Tech/Processed) のために必要。
# gmail.readonly では mark_processed が動作しない (ADR-009 参照)。
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_MODAL_SECRET_NAME = "gmail-oauth"
_ENV_VAR_NAME = "GMAIL_OAUTH_JSON"

logger = logging.getLogger(__name__)


def build_modal_secret_command(secret_name: str, env_var: str, json_payload: str) -> str:
    """Modal Secrets 登録コマンドを組み立てる。"""
    return f"modal secret create {shlex.quote(secret_name)} {env_var}={shlex.quote(json_payload)}"


def main() -> None:
    # argparse: コマンドライン引数を宣言的に定義する標準ライブラリの CLI パーサー
    parser = argparse.ArgumentParser(
        description="Gmail OAuth フローを実行し、Modal Secrets 登録コマンドを出力する"
    )
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="OAuth client シークレットファイル (既定: credentials.json)",
    )
    parser.add_argument(
        "--output",
        default="gmail_oauth.json",
        help="出力する認証情報ファイル (既定: gmail_oauth.json)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="ローカルサーバのポート番号 (0 = 自動採番, 既定: 0)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    credentials_path = Path(args.credentials)
    if not credentials_path.exists():
        logger.error(
            "%s が見つかりません。"
            "Google Cloud Console の「APIs & Services > Credentials」で"
            "「OAuth client ID (Desktop)」を作成し、JSON をダウンロードしてください。",
            args.credentials,
        )
        raise SystemExit(1)

    logger.info("OAuth フローを開始します (スコープ: %s)", SCOPES[0])
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=args.port)

    output_path = Path(args.output)
    json_str: str = creds.to_json()
    output_path.write_text(json_str, encoding="utf-8")
    os.chmod(output_path, 0o600)
    logger.info("認証情報を %s に書き出しました (パーミッション: 0o600)", args.output)

    command = build_modal_secret_command(_MODAL_SECRET_NAME, _ENV_VAR_NAME, json_str)
    print("\n以下のコマンドで Modal Secrets に登録してください:\n")
    print(f"  {command}\n")
    print("登録後は gmail_oauth.json と credentials.json をローカルに保管し、")
    print("リポジトリにはコミットしないでください。")


if __name__ == "__main__":
    main()
