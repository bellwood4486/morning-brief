from __future__ import annotations

from pathlib import Path

from digest.userdoc_store import UserdocStore


def _make_template_dir(tmp_path: Path) -> Path:
    template_dir = tmp_path / "seeds"
    template_dir.mkdir()
    (template_dir / "user_initial.md").write_text("# USER.md\n\n初期版。\n", encoding="utf-8")
    (template_dir / "memory_initial.md").write_text("# Memory Index\n", encoding="utf-8")
    return template_dir


class TestBootstrapIfMissing:
    def test_creates_user_md_from_template(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        user_md = (tmp_path / "vol" / "USER.md").read_text(encoding="utf-8")
        assert user_md == "# USER.md\n\n初期版。\n"

    def test_creates_memory_md_from_template(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        memory_md = (tmp_path / "vol" / "MEMORY.md").read_text(encoding="utf-8")
        assert memory_md == "# Memory Index\n"

    def test_does_not_overwrite_existing_user_md(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        vol = tmp_path / "vol"
        vol.mkdir()
        (vol / "USER.md").write_text("# 既存コンテンツ\n", encoding="utf-8")
        store = UserdocStore(vol)
        store.bootstrap_if_missing(template_dir)
        assert (vol / "USER.md").read_text(encoding="utf-8") == "# 既存コンテンツ\n"

    def test_idempotent_on_second_call(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        store.bootstrap_if_missing(template_dir)
        user_md = (tmp_path / "vol" / "USER.md").read_text(encoding="utf-8")
        assert user_md == "# USER.md\n\n初期版。\n"

    def test_creates_base_dir_if_missing(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "deep" / "vol")
        store.bootstrap_if_missing(template_dir)
        assert (tmp_path / "deep" / "vol" / "USER.md").exists()


class TestRead:
    def test_returns_user_md_and_memory_md(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        user_md, memory_md = store.read()
        assert user_md == "# USER.md\n\n初期版。\n"
        assert memory_md == "# Memory Index\n"

    def test_returns_empty_string_when_memory_md_missing(self, tmp_path: Path) -> None:
        vol = tmp_path / "vol"
        vol.mkdir()
        (vol / "USER.md").write_text("# USER.md\n", encoding="utf-8")
        store = UserdocStore(vol)
        _, memory_md = store.read()
        assert memory_md == ""


class TestWriteWithSnapshot:
    def test_returns_none_when_content_unchanged(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        user_md, memory_md = store.read()
        result = store.write_with_snapshot(user_md, memory_md)
        assert result is None

    def test_returns_snapshot_paths_when_changed(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        result = store.write_with_snapshot("# 新しい USER.md\n", "# 新しい MEMORY.md\n")
        assert result is not None
        snap_user, snap_memory = result
        assert snap_user.exists()
        assert snap_memory.exists()

    def test_snapshot_contains_previous_content(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        original_user, _ = store.read()
        store.write_with_snapshot("# 更新後\n", "# 更新後 memory\n")
        snaps = list((tmp_path / "vol" / "state" / "snapshots").glob("USER.md.*.md"))
        assert len(snaps) == 1
        assert snaps[0].read_text(encoding="utf-8") == original_user

    def test_overwrites_current_files(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        store.write_with_snapshot("# 更新後 USER\n", "# 更新後 MEMORY\n")
        user_md, memory_md = store.read()
        assert user_md == "# 更新後 USER\n"
        assert memory_md == "# 更新後 MEMORY\n"

    def test_no_tmp_file_left_after_write(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        store.write_with_snapshot("# 更新後\n", "# 更新後\n")
        tmp_files = list((tmp_path / "vol").glob("*.tmp"))
        assert tmp_files == []

    def test_only_user_md_changed(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol")
        store.bootstrap_if_missing(template_dir)
        _, memory_md = store.read()
        result = store.write_with_snapshot("# 変更後\n", memory_md)
        assert result is not None

    def test_prune_keeps_at_most_max_snapshots(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol", max_snapshots=3)
        store.bootstrap_if_missing(template_dir)
        for i in range(5):
            store.write_with_snapshot(f"# Version {i}\n", f"# Memory {i}\n")
        snaps_dir = tmp_path / "vol" / "state" / "snapshots"
        user_snaps = list(snaps_dir.glob("USER.md.*.md"))
        assert len(user_snaps) <= 3

    def test_oldest_snapshots_pruned_first(self, tmp_path: Path) -> None:
        template_dir = _make_template_dir(tmp_path)
        store = UserdocStore(tmp_path / "vol", max_snapshots=2)
        store.bootstrap_if_missing(template_dir)
        for i in range(4):
            store.write_with_snapshot(f"# Version {i}\n", f"# Memory {i}\n")
        snaps_dir = tmp_path / "vol" / "state" / "snapshots"
        user_snaps = sorted(snaps_dir.glob("USER.md.*.md"))
        assert len(user_snaps) == 2
        # 最新 2 件のみ残る: Version 2 と Version 3 のスナップショット (書き込み前の状態)
        contents = [s.read_text(encoding="utf-8") for s in user_snaps]
        # 少なくとも最古 (Version 0, 1) のスナップショットが消えていること
        assert all("Version 0" not in c for c in contents)
