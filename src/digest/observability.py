"""
設計境界: langsmith / logfire の import はこのファイル限定 (アーキテクチャテストで強制)。
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Generator
from typing import Any, ParamSpec, TypeVar

import langsmith
import logfire

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

_logfire_initialized = False


def init_observability(dry_run: bool, run_id: str) -> None:
    """LangSmith と Logfire を初期化する。クレデンシャル未設定時は no-op。"""
    global _logfire_initialized

    api_key = os.environ.get("LANGSMITH_API_KEY")
    if api_key:
        project = "morning-brief-dev" if dry_run else "morning-brief"
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ["LANGSMITH_PROJECT"] = project
        logger.info("LangSmith enabled: project=%s run_id=%s", project, run_id)

    token = os.environ.get("LOGFIRE_TOKEN")
    if token:
        logfire.configure(
            token=token,
            service_name="morning-brief",
            environment="dry-run" if dry_run else "production",
        )
        logfire.info("observability initialized", run_id=run_id)
        _logfire_initialized = True
        logger.info("Logfire enabled run_id=%s", run_id)


def trace_llm(name: str, **metadata: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """LangSmith @traceable の薄いラッパ。LANGSMITH_TRACING=true 時のみ実際にトレースする。"""
    return langsmith.traceable(name=name, metadata=metadata)  # type: ignore[return-value]


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Logfire span の薄いラッパ。Logfire 未初期化時は no-op。"""
    if not _logfire_initialized:
        yield None
        return
    with logfire.span(name, **attributes) as s:
        yield s


def flush() -> None:
    """Logfire スパンを強制フラッシュする。Modal short-lived 関数の終了直前に呼ぶ。"""
    if _logfire_initialized:
        logfire.force_flush()
