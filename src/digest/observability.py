"""
設計境界: logfire の import はこのファイル限定 (アーキテクチャテストで強制)。
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Generator
from typing import Any

import logfire

logger = logging.getLogger(__name__)

_logfire_initialized = False


def init_observability(dry_run: bool, run_id: str) -> None:
    """Logfire を初期化する。クレデンシャル未設定時は no-op。"""
    global _logfire_initialized

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    token = os.environ.get("LOGFIRE_TOKEN")
    if token:
        logfire.configure(
            token=token,
            service_name="morning-brief",
            environment="dev" if dry_run else "prod",
        )
        root = logging.getLogger()
        if not any(isinstance(h, logfire.LogfireLoggingHandler) for h in root.handlers):
            root.addHandler(logfire.LogfireLoggingHandler(level=logging.INFO))
        logfire.info("observability initialized", run_id=run_id)
        _logfire_initialized = True
        logger.info("Logfire enabled run_id=%s", run_id)


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Logfire span の薄いラッパ。Logfire 未初期化時は no-op。"""
    if not _logfire_initialized:
        yield None
        return
    with logfire.span(name, **attributes) as s:
        yield s


def flush() -> None:
    """Logfire スパンを強制フラッシュし exporter を閉じる。
    Modal short-lived 関数の終了直前に呼ぶ。
    """
    if _logfire_initialized:
        logfire.force_flush()
        logfire.shutdown()
