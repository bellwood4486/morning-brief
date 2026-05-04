from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_USER_MD = "USER.md"
_MEMORY_MD = "MEMORY.md"
_SNAPSHOTS_DIR = "state/snapshots"


class UserdocStore:
    """Modal Volume 上の USER.md / MEMORY.md の読み書きと世代スナップショット管理。

    StateStore (feedback.jsonl / last_digest.json) とは責務を分離している。
    feedback は追記ストリーム、userdoc は単一ファイルの世代管理という性質差がある。
    """

    def __init__(self, base_dir: Path, max_snapshots: int = 30) -> None:
        self._base_dir = base_dir
        self._max_snapshots = max_snapshots

    @property
    def _user_md_path(self) -> Path:
        return self._base_dir / _USER_MD

    @property
    def _memory_md_path(self) -> Path:
        return self._base_dir / _MEMORY_MD

    @property
    def _snapshots_dir(self) -> Path:
        return self._base_dir / _SNAPSHOTS_DIR

    def bootstrap_if_missing(self, template_dir: Path) -> None:
        """USER.md / MEMORY.md が Volume に無ければ template_dir からコピーする。

        既存ファイルは上書きしない (再起動冪等)。
        - USER.md ← template_dir/user_initial.md
        - MEMORY.md ← template_dir/memory_initial.md
        """
        self._base_dir.mkdir(parents=True, exist_ok=True)
        if not self._user_md_path.exists():
            src = template_dir / "user_initial.md"
            shutil.copy2(src, self._user_md_path)
            logger.info("UserdocStore: bootstrapped USER.md from %s", src)
        if not self._memory_md_path.exists():
            src = template_dir / "memory_initial.md"
            shutil.copy2(src, self._memory_md_path)
            logger.info("UserdocStore: bootstrapped MEMORY.md from %s", src)

    def read(self) -> tuple[str, str]:
        """(user_md, memory_md) を返す。bootstrap 後を前提とする。"""
        user_md = self._user_md_path.read_text(encoding="utf-8")
        memory_md = (
            self._memory_md_path.read_text(encoding="utf-8")
            if self._memory_md_path.exists()
            else ""
        )
        return user_md, memory_md

    def write_with_snapshot(
        self,
        new_user_md: str,
        new_memory_md: str,
    ) -> tuple[Path, Path] | None:
        """変更があれば snapshot を取って上書きし (snapshot_user, snapshot_memory) を返す。

        変更なし (byte-equal) なら None を返す。
        snapshot は state/snapshots/ 配下に UTC タイムスタンプ付きで保存する。
        snapshot 数が max_snapshots を超えたら古い順に削除する。
        書き込みは一時ファイル + os.replace で原子的に行う。
        """
        current_user, current_memory = self.read()
        if new_user_md == current_user and new_memory_md == current_memory:
            return None

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        self._snapshots_dir.mkdir(parents=True, exist_ok=True)

        snap_user = self._snapshots_dir / f"USER.md.{timestamp}.md"
        snap_memory = self._snapshots_dir / f"MEMORY.md.{timestamp}.md"
        shutil.copy2(self._user_md_path, snap_user)
        if self._memory_md_path.exists():
            shutil.copy2(self._memory_md_path, snap_memory)
        else:
            snap_memory.write_text("", encoding="utf-8")

        self._atomic_write(self._user_md_path, new_user_md)
        self._atomic_write(self._memory_md_path, new_memory_md)

        self._prune_snapshots()

        logger.info("UserdocStore: wrote USER.md/MEMORY.md, snapshot=%s", timestamp)
        return snap_user, snap_memory

    def _atomic_write(self, dest: Path, content: str) -> None:
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(dest)

    def _prune_snapshots(self) -> None:
        user_snaps = sorted(self._snapshots_dir.glob("USER.md.*.md"))
        memory_snaps = sorted(self._snapshots_dir.glob("MEMORY.md.*.md"))
        for snaps in (user_snaps, memory_snaps):
            excess = len(snaps) - self._max_snapshots
            for old in snaps[:excess]:
                old.unlink(missing_ok=True)


def build_userdoc_store(base_dir: Path, max_snapshots: int = 30) -> UserdocStore:
    return UserdocStore(base_dir, max_snapshots=max_snapshots)
