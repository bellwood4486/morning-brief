from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import modal

logger = logging.getLogger(__name__)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "google-genai",
        "slack-sdk",
        "google-api-python-client",
        "google-auth-oauthlib",
        "pydantic>=2",
        "pyyaml",
        "langsmith>=0.2",
        "logfire>=2",
    )
    # digest パッケージを /root/src に配置し PYTHONPATH で参照できるようにする。
    # add_local_dir("src", ...) にすると seeds.py の parents[2] が /root になり
    # /root/seeds と一致する。src/digest を直接マウントすると parents[2] = / になり破綻する。
    .env({"PYTHONPATH": "/root/src"})
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("seeds", remote_path="/root/seeds")
    .add_local_file("config.yaml", remote_path="/root/config.yaml")
)
volume = modal.Volume.from_name("morning-brief-hermes", create_if_missing=True)
app = modal.App("morning-brief")


@app.function(
    image=image,
    schedule=modal.Cron("30 21 * * 1-5"),  # 平日 06:30 JST (= UTC 21:30 前日)
    secrets=[
        modal.Secret.from_name("gmail-oauth"),
        modal.Secret.from_name("gemini-api-key"),
        modal.Secret.from_name("slack-bot-token"),
        modal.Secret.from_name("langsmith"),
        modal.Secret.from_name("logfire"),
    ],
    volumes={"/root/.hermes": volume},
    timeout=600,
)
def digest_job(dry_run: bool = False) -> None:
    # Modal コンテナ内でのみ解決できるため、ここで遅延 import する。
    from digest.config import Config
    from digest.formatter import (
        digest_fallback_text,
        empty_digest_blocks,
        empty_digest_fallback_text,
        to_block_kit,
    )
    from digest.gmail_client import build_gmail_client
    from digest.hermes_bridge import build_hermes_bridge
    from digest.notifiers.slack import build_slack_notifier
    from digest.observability import flush, init_observability, span
    from digest.seeds import load_seed
    from digest.summarize import build_gemini_client

    # run_id は LangSmith run と Logfire span を後から突き合わせるための相関 ID
    run_id = uuid.uuid4().hex[:12]
    init_observability(dry_run, run_id)

    cfg = Config.load(Path("/root/config.yaml"))
    notifier = build_slack_notifier(os.environ["SLACK_BOT_TOKEN"], cfg.slack.digest_channel)
    alerts = build_slack_notifier(os.environ["SLACK_BOT_TOKEN"], cfg.slack.alerts_channel)
    gmail = build_gmail_client(os.environ["GMAIL_OAUTH_JSON"], cfg.gmail.processed_label)
    gemini = build_gemini_client(os.environ["GEMINI_API_KEY"])
    hermes = build_hermes_bridge()

    try:
        with span("digest_job", run_id=run_id, dry_run=str(dry_run)):
            with span("phase1.collect_feedback"):
                try:
                    _phase1_collect_feedback(notifier, hermes)
                except Exception:
                    logger.warning("Phase 1 (collect feedback) failed", exc_info=True)

            with span("phase2.fetch_emails"):
                emails = _phase2_fetch_emails(gmail, cfg.gmail.label, cfg.gmail.lookback_hours)

            if not emails:
                generated_at = datetime.now(UTC)
                blocks = empty_digest_blocks(generated_at=generated_at)
                text = empty_digest_fallback_text(generated_at)
                with span("phase4.publish_empty"):
                    _phase4_publish_empty(notifier, blocks, text, dry_run)
                return

            with span("phase3.summarize"):
                try:
                    digest = _phase3_summarize(
                        gemini, emails, load_seed("summarize_prompt.md"), cfg.llm.model
                    )
                except Exception as e:
                    logger.exception("Phase 3 (summarize) failed")
                    _alert(alerts, f"Phase 3 (summarize) failed: {e}")
                    return

            blocks = to_block_kit(digest)
            text = digest_fallback_text(digest)
            with span("phase4.publish"):
                try:
                    posted = _phase4_publish(notifier, blocks, text, dry_run)
                except Exception as e:
                    logger.exception("Phase 4 (send) failed")
                    _alert(alerts, f"Phase 4 (send) failed: {e}")
                    _print_for_dry_run(blocks, digest)
                    return

            if posted is not None:
                hermes.set_last_message_id(posted.message_id)

            with span("phase5.postprocess"):
                _phase5_postprocess(gmail, hermes, emails, dry_run)
    finally:
        flush()


# --- Phase 関数 ---
# 各 Phase はロジックを持たず、対応モジュールへの委譲のみを行う (design.md §2.1)。
# 引数型は Any: modal_app.py は mypy/pyright 対象外 (CLAUDE.md §実装方針 参照)。


def _phase1_collect_feedback(notifier: Any, hermes: Any) -> None:
    message_id = hermes.get_last_message_id()
    if message_id is None:
        # 初回起動時は前日メッセージが存在しないため収集を skip する。
        logger.info("Phase 1: no previous message_id, skipping feedback collection")
        return
    feedbacks = notifier.collect_feedback(message_id)
    hermes.inject_feedback(feedbacks)
    logger.info("Phase 1: collected %d feedbacks", len(feedbacks))


def _phase2_fetch_emails(gmail: Any, label: str, lookback_hours: int) -> list[Any]:
    emails = gmail.fetch_unread(label, timedelta(hours=lookback_hours))
    logger.info("Phase 2: fetched %d emails (label=%s)", len(emails), label)
    return emails


def _phase3_summarize(gemini: Any, emails: list[Any], prompt: str, model: str) -> Any:
    digest = gemini.summarize(emails, prompt, model)
    logger.info(
        "Phase 3: summarized %d tldr_items, %d details",
        len(digest.tldr_items),
        len(digest.details),
    )
    return digest


def _phase4_publish(notifier: Any, blocks: list[Any], text: str, dry_run: bool) -> Any:
    if dry_run:
        _print_for_dry_run(blocks)
        return None
    posted = notifier.send(blocks, text=text)
    logger.info("Phase 4: posted message_id=%s", posted.message_id)
    return posted


def _phase4_publish_empty(notifier: Any, blocks: list[Any], text: str, dry_run: bool) -> None:
    if dry_run:
        _print_for_dry_run(blocks)
        logger.info("Phase 4: dry_run=True, empty digest not sent")
        return
    notifier.send(blocks, text=text)
    logger.info("Phase 4: posted empty digest")


def _phase5_postprocess(gmail: Any, hermes: Any, emails: list[Any], dry_run: bool) -> None:
    if dry_run:
        logger.info("Phase 5: dry_run=True, skipping Gmail label and Hermes observe")
        return
    gmail.mark_processed(emails)
    logger.info("Phase 5: marked %d emails as processed", len(emails))


def _alert(alerts: Any, message: str) -> None:
    try:
        alerts.send(
            [{"type": "section", "text": {"type": "mrkdwn", "text": message}}],
            text=f"[morning-brief alert] {message}",
        )
    except Exception:
        logger.error("Failed to send alert: %s", message, exc_info=True)


def _print_for_dry_run(blocks: list[Any], digest: Any = None) -> None:
    print("=== Block Kit ===")
    print(json.dumps(blocks, indent=2, ensure_ascii=False))
    if digest is not None:
        print("=== Digest (JSON) ===")
        print(digest.model_dump_json(indent=2))
