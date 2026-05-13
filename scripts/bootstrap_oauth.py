#!/usr/bin/env python
"""Gmail OAuth 認証情報を取得して Modal Secrets に自動登録するローカル実行スクリプト。"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

# Desktop OAuth フロー: ブラウザを起動してリダイレクト URI をローカルサーバで受け取る
from google_auth_oauthlib.flow import InstalledAppFlow

# gmail.modify: メッセージ読み取り + ラベル付与 (Newsletter/Tech/Processed) のために必要。
# gmail.readonly では mark_processed が動作しない (ADR-009 参照)。
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_DEFAULT_MODAL_SECRET_NAME = "gmail-oauth"
_ENV_VAR_NAME = "GMAIL_OAUTH_JSON"

logger = logging.getLogger(__name__)


def register_modal_secret(secret_name: str, json_payload: str) -> None:
    """json_payload を subprocess 経由で Modal Secrets に登録する。"""
    result = subprocess.run(
        [
            "uv",
            "run",
            "modal",
            "secret",
            "create",
            "--force",
            secret_name,
            f"{_ENV_VAR_NAME}={json_payload}",
        ],
        check=False,
    )
    if result.returncode != 0:
        print(
            "自動登録に失敗しました。uv run modal token new 済みか確認してから、"
            f"gmail_oauth.json を cat して手動で登録してください:\n"
            f"  uv run modal secret create --force {secret_name}"
            f' {_ENV_VAR_NAME}="$(cat gmail_oauth.json)"',
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"{secret_name} を Modal Secrets に登録しました。", file=sys.stderr)
    print(
        "gmail_oauth.json と credentials.json をローカルに保管し、"
        "リポジトリにはコミットしないでください。",
        file=sys.stderr,
    )


def main() -> None:
    # argparse: コマンドライン引数を宣言的に定義する標準ライブラリの CLI パーサー
    parser = argparse.ArgumentParser(
        description="Gmail OAuth フローを実行し、Modal Secrets に自動登録する"
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
    parser.add_argument(
        "--secret-name",
        default=_DEFAULT_MODAL_SECRET_NAME,
        help=f"Modal Secrets の名前 (既定: {_DEFAULT_MODAL_SECRET_NAME})",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="Modal Secrets への登録をスキップして JSON 生成のみ行う",
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

    if not args.no_register:
        register_modal_secret(args.secret_name, json_str)


if __name__ == "__main__":
    main()
