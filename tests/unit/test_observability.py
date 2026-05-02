"""observability モジュールのユニットテスト。"""

from __future__ import annotations

import pytest


def test_init_observability_no_credentials_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """クレデンシャルが一切ない環境でも例外を出さない。"""
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)

    # observability モジュールのグローバル状態をリセットするため再 import する。
    import importlib

    import digest.observability as obs_mod

    importlib.reload(obs_mod)

    obs_mod.init_observability(dry_run=True, run_id="test000")

    assert obs_mod._logfire_initialized is False


def test_trace_llm_passthrough_without_langsmith(monkeypatch: pytest.MonkeyPatch) -> None:
    """LANGSMITH_TRACING 未設定時は @trace_llm が関数を素通しで呼ぶ。"""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    from digest.observability import trace_llm

    call_log: list[str] = []

    @trace_llm("test.func")
    def dummy(x: int) -> int:
        call_log.append(f"called:{x}")
        return x * 2

    result = dummy(5)

    assert result == 10
    assert call_log == ["called:5"]


def test_span_noop_without_logfire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logfire 未初期化時は span が no-op で例外を出さない。"""
    import importlib

    import digest.observability as obs_mod

    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    importlib.reload(obs_mod)

    # _logfire_initialized=False の状態で span を使う
    entered = False
    with obs_mod.span("test.span", key="val") as s:
        entered = True
        assert s is None

    assert entered


def test_flush_noop_without_logfire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logfire 未初期化時は flush が no-op で例外を出さない。"""
    import importlib

    import digest.observability as obs_mod

    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    importlib.reload(obs_mod)

    obs_mod.flush()  # 例外が出なければ OK
