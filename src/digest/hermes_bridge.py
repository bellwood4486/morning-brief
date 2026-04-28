from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from digest.models import Feedback

logger = logging.getLogger(__name__)


# 責務: Modal Volume `~/.hermes/` への永続状態の読み書きと Hermes へのフィードバック注入を仲介する。
@dataclass(frozen=True)
class HermesBridge:
    state_dir: Path

    # @property: メソッドをフィールド風にアクセスできるデコレータ。括弧なしで呼べる。
    @property
    def _state_file(self) -> Path:
        return self.state_dir / "state" / "last_digest.json"

    def get_last_message_id(self) -> str | None:
        if not self._state_file.exists():
            return None
        data: dict[str, object] = json.loads(self._state_file.read_text(encoding="utf-8"))
        val = data.get("message_id")
        return str(val) if val is not None else None

    def set_last_message_id(self, message_id: str) -> None:
        """指定 message_id を原子的に永続化する。同値で複数回呼んでも結果は同一 (冪等)。

        Phase 4 全体としてのリトライ冪等性は呼び出し側 (modal_app.py) の責務。
        """
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        # 一時ファイルに書いてから os.replace でリネームする (POSIX の atomic rename)。
        # Path.write_text 直接書き込みだと truncate → write の途中でクラッシュした場合に
        # 空ファイル/途中切れ JSON が残り、翌朝 Phase 1 が JSONDecodeError で詰むため避ける。
        tmp = self._state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"message_id": message_id}), encoding="utf-8")
        os.replace(tmp, self._state_file)

    def inject_feedback(self, feedbacks: list[Feedback]) -> None:
        # TODO(Sprint 2 / T2.2): Hermes 側へ反映するロジックを追加
        logger.info("inject_feedback called: count=%d", len(feedbacks))

    def observe_session(self, session_log: dict[str, Any]) -> None:
        # TODO(Sprint 2 / T2.3): セッションログを Hermes へ渡してスキル自動生成をトリガ
        logger.info("observe_session called: keys=%s", sorted(session_log.keys()))


def build_hermes_bridge(state_dir: Path = Path("/root/.hermes")) -> HermesBridge:
    return HermesBridge(state_dir=state_dir)
