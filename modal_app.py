from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import modal

logger = logging.getLogger(__name__)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "pydantic-ai[google]",
        "slack-sdk",
        "google-api-python-client",
        "google-auth-oauthlib",
        "pydantic>=2",
        "pyyaml",
        "logfire>=2",
    )
    # digest パッケージを /root/src に配置し PYTHONPATH で参照できるようにする。
    # add_local_dir("src", ...) にすると seeds.py の parents[2] が /root になり
    # /root/seeds と一致する。src/digest を直接マウントすると parents[2] = / になり破綻する。
    .env({"PYTHONPATH": "/root/src"})
    .add_local_dir("src", remote_path="/root/src")
    .add_local_dir("seeds", remote_path="/root/seeds")
)
volume = modal.Volume.from_name("morning-brief-state", create_if_missing=True)
app = modal.App("morning-brief")

_VOLUME_MOUNT = Path("/root/.brief")
_SEEDS_DIR = Path("/root/seeds")


@app.function(
    image=image,
    schedule=modal.Cron("30 21 * * *"),  # 毎日 06:30 JST (= UTC 21:30 前日)
    secrets=[
        modal.Secret.from_name("gmail-oauth"),
        modal.Secret.from_name("gemini-api-key"),
        modal.Secret.from_name("slack-bot-token"),
        modal.Secret.from_name("logfire"),
    ],
    volumes={str(_VOLUME_MOUNT): volume},
    timeout=600,
)
def digest_job(dry_run: bool = False) -> None:
    # Modal コンテナ内でのみ解決できるため、ここで遅延 import する。
    from digest.config import Config
    from digest.formatter import digest_fallback_text, to_block_kit
    from digest.gmail_client import build_gmail_client
    from digest.notifiers.slack import build_slack_notifier
    from digest.observability import flush, init_observability, span
    from digest.operations_notifier import (
        PhaseError,
        RunSummary,
        build_operations_run_summary_notifier,
    )
    from digest.seeds import load_seed
    from digest.state_store import build_state_store
    from digest.summarize import build_gemini_client
    from digest.user_md_updater import build_user_md_updater
    from digest.userdoc_notifier import build_userdoc_notifier
    from digest.userdoc_store import build_userdoc_store

    run_id = uuid.uuid4().hex[:12]
    init_observability(dry_run, run_id)

    cfg = Config.load(_VOLUME_MOUNT / "config.yaml")
    notifier = build_slack_notifier(os.environ["SLACK_BOT_TOKEN"], cfg.slack.digest_channel)
    operations_slack = build_slack_notifier(
        os.environ["SLACK_BOT_TOKEN"], cfg.slack.operations_channel
    )
    gmail = build_gmail_client(os.environ["GMAIL_OAUTH_JSON"], cfg.gmail.processed_label)
    gemini = build_gemini_client(os.environ["GEMINI_API_KEY"])
    state_store = build_state_store(_VOLUME_MOUNT)
    userdoc_store = build_userdoc_store(_VOLUME_MOUNT)
    user_md_updater = build_user_md_updater(
        api_key=os.environ["GEMINI_API_KEY"],
        model_name=cfg.llm.model,
    )
    userdoc_notifier = build_userdoc_notifier(operations_slack)
    ops_summary_notifier = build_operations_run_summary_notifier(operations_slack)

    userdoc_store.bootstrap_if_missing(_SEEDS_DIR)

    summary = RunSummary(status="error")

    try:
        with span("digest_job", run_id=run_id, dry_run=str(dry_run)):
            with span("phase1.collect_feedback"):
                try:
                    _phase1_collect_feedback(notifier, state_store, dry_run)
                except Exception as e:
                    summary.errors.append(PhaseError("phase1", str(e)))
                    logger.warning("Phase 1 (collect_feedback) failed: %s", e, exc_info=True)

            with span("phase2.fetch_emails"):
                try:
                    emails = _phase2_fetch_emails(gmail, cfg.gmail.label, cfg.gmail.lookback_hours)
                except Exception as e:
                    summary.errors.append(PhaseError("phase2", str(e)))
                    logger.exception("Phase 2 (fetch_emails) failed")
                    return

            if not emails:
                summary.status = "empty"
                return

            with span("phase3.summarize"):
                try:
                    digest = _phase3_summarize(
                        gemini, emails, load_seed("summarize_prompt.md"), cfg.llm.model
                    )
                except Exception as e:
                    summary.errors.append(PhaseError("phase3", str(e)))
                    logger.exception("Phase 3 (summarize) failed")
                    return

            blocks = to_block_kit(digest)
            text = digest_fallback_text(digest)
            with span("phase4.publish"):
                try:
                    posted = _phase4_publish(notifier, blocks, text, dry_run)
                    if posted is not None:
                        state_store.set_last_message_id(posted.message_id)
                        summary.digest_message_id = posted.message_id
                    summary.digest_count = len(emails)
                    summary.status = "ok"
                except Exception as e:
                    summary.errors.append(PhaseError("phase4", str(e)))
                    logger.exception("Phase 4 (send) failed")
                    _print_for_dry_run(blocks, digest)
                    return

            with span("phase5.postprocess"):
                userdoc_updated, phase5_errors = _phase5_postprocess(
                    gmail,
                    emails,
                    dry_run,
                    state_store,
                    userdoc_store,
                    user_md_updater,
                    userdoc_notifier,
                    run_id,
                )
                summary.userdoc_updated = userdoc_updated
                summary.errors.extend(phase5_errors)
    finally:
        ops_summary_notifier.notify(summary, dry_run=dry_run)
        flush()


# --- Phase 関数 ---
# 各 Phase はロジックを持たず、対応モジュールへの委譲のみを行う (design.md §2.1)。
# 引数型は Any: modal_app.py は mypy/pyright 対象外 (CLAUDE.md §実装方針 参照)。


def _phase1_collect_feedback(notifier: Any, state_store: Any, dry_run: bool) -> None:
    message_id = state_store.get_last_message_id()
    if message_id is None:
        logger.info("Phase 1: no previous message_id, skipping feedback collection")
        return
    feedbacks = notifier.collect_feedback(message_id)
    logger.info("Phase 1: collected %d feedbacks for message_id=%s", len(feedbacks), message_id)
    if not dry_run:
        state_store.append_feedback(feedbacks)
    else:
        logger.info("Phase 1: dry_run=True, skip append (%d items)", len(feedbacks))


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


def _phase5_postprocess(
    gmail: Any,
    emails: list[Any],
    dry_run: bool,
    state_store: Any,
    userdoc_store: Any,
    user_md_updater: Any,
    userdoc_notifier: Any,
    run_id: str,
) -> tuple[bool, list[Any]]:
    """Phase 5 を実行し (userdoc_updated, errors) を返す。"""
    errors: list[Any] = []

    if dry_run:
        logger.info("Phase 5: dry_run=True, skipping Gmail label")
    else:
        gmail.mark_processed(emails)
        logger.info("Phase 5: marked %d emails as processed", len(emails))

    diff = user_md_updater.update_if_ready(
        feedback_log_path=state_store.feedback_path,
        userdoc_store=userdoc_store,
    )
    if diff is None:
        return False, errors

    if dry_run:
        _print_userdoc_dry_run(diff)
        return False, errors

    before_user, before_memory = userdoc_store.read()

    snapshots = userdoc_store.write_with_snapshot(
        new_user_md=diff.user_md_content,
        new_memory_md=diff.memory_md_content,
    )
    if snapshots is None:
        logger.info("Phase 5: USER.md unchanged after diff, skip notify")
        return False, errors
    snap_user, snap_memory = snapshots
    logger.info("Phase 5: wrote USER.md/MEMORY.md, snapshot=%s", snap_user.name)

    try:
        userdoc_notifier.notify(
            diff=diff,
            before_user=before_user,
            after_user=diff.user_md_content,
            before_memory=before_memory,
            after_memory=diff.memory_md_content,
            snapshot_user_path=snap_user,
            snapshot_memory_path=snap_memory,
        )
        state_store.rotate_feedback(suffix=f"userdoc-{snap_user.stem}")
        logger.info("Phase 5: userdoc notify sent, feedback rotated")
        return True, errors
    except Exception as e:
        logger.warning("Phase 5 userdoc notify failed: %s", e, exc_info=True)
        errors.append(_make_phase_error("phase5.userdoc_notify", e))
        return True, errors


def _make_phase_error(phase: str, exc: Exception) -> Any:
    # PhaseError を遅延 import せずに生成するためのヘルパ。
    # modal_app.py は型チェック対象外のため Any を返す。
    from digest.operations_notifier import PhaseError

    return PhaseError(phase=phase, message=str(exc))


def _print_for_dry_run(blocks: list[Any], digest: Any = None) -> None:
    print("=== Block Kit ===")
    print(json.dumps(blocks, indent=2, ensure_ascii=False))
    if digest is not None:
        print("=== Digest (JSON) ===")
        print(digest.model_dump_json(indent=2))


def _print_userdoc_dry_run(diff: Any) -> None:
    print("=== UserMdDiff (dry_run) ===")
    print(f"change_summary: {diff.change_summary}")
    print(f"USER.md (head):\n{diff.user_md_content[:500]}")
    if len(diff.user_md_content) > 500:
        print("... (truncated)")
    print(f"MEMORY.md (head):\n{diff.memory_md_content[:200]}")
    if len(diff.memory_md_content) > 200:
        print("... (truncated)")
