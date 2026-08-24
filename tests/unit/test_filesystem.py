"""Unit tests for core.filesystem (session 03).

Everything runs against a fake $HOME / XDG environment (see the
``fake_home`` fixture in conftest) — never against the real user tree.
"""

from __future__ import annotations

import os

import pytest

from core import filesystem


class TestXdgResolution:
    def test_defaults_under_home(self, fake_home):
        assert filesystem.xdg_config_home() == fake_home / ".config"
        assert filesystem.xdg_data_home() == fake_home / ".local" / "share"
        assert filesystem.xdg_state_home() == fake_home / ".local" / "state"
        assert filesystem.omni_config_dir() == fake_home / ".config" / "omni-theme"
        assert filesystem.omni_state_dir() == (
            fake_home / ".local" / "state" / "omni-theme"
        )

    def test_env_overrides(self, fake_home, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / "cfg"))
        monkeypatch.setenv("XDG_DATA_HOME", str(fake_home / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(fake_home / "state"))
        assert filesystem.omni_config_dir() == fake_home / "cfg" / "omni-theme"
        assert filesystem.omni_data_dir() == fake_home / "data" / "omni-theme"
        state = fake_home / "state" / "omni-theme"
        assert filesystem.state_current_dir() == state / "current"
        assert filesystem.state_previous_dir() == state / "previous"
        assert filesystem.state_staging_dir() == state / "staging"
        assert filesystem.state_backups_dir() == state / "backups"

    def test_read_at_call_time_not_import_time(self, fake_home, monkeypatch):
        before = filesystem.omni_state_dir()
        monkeypatch.setenv("XDG_STATE_HOME", str(fake_home / "elsewhere"))
        after = filesystem.omni_state_dir()
        assert before != after


class TestAtomicWrite:
    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "file.conf"
        filesystem.atomic_write(target, b"data")
        assert target.read_bytes() == b"data"

    def test_overwrites_existing_content(self, tmp_path):
        target = tmp_path / "f"
        filesystem.atomic_write(target, b"old")
        filesystem.atomic_write(target, b"new")
        assert target.read_bytes() == b"new"

    def test_preserves_existing_mode(self, tmp_path):
        target = tmp_path / "secret"
        filesystem.atomic_write(target, b"x")
        os.chmod(target, 0o600)
        filesystem.atomic_write(target, b"y")
        assert (target.stat().st_mode & 0o777) == 0o600

    def test_explicit_mode_for_new_file(self, tmp_path):
        target = tmp_path / "f"
        filesystem.atomic_write(target, b"x", mode=0o640)
        assert (target.stat().st_mode & 0o777) == 0o640

    def test_no_temp_files_left_behind(self, tmp_path):
        target = tmp_path / "f"
        for i in range(3):
            filesystem.atomic_write(target, f"v{i}".encode())
        assert [p.name for p in tmp_path.iterdir()] == ["f"]

    def test_failed_replace_keeps_old_content(self, tmp_path, monkeypatch):
        target = tmp_path / "f"
        filesystem.atomic_write(target, b"original")

        def boom(*a, **k):
            raise OSError("replace failed")

        monkeypatch.setattr(filesystem.os, "replace", boom)
        with pytest.raises(OSError):
            filesystem.atomic_write(target, b"clobber")
        assert target.read_bytes() == b"original"

    def test_atomic_write_text_utf8(self, tmp_path):
        target = tmp_path / "t.txt"
        filesystem.atomic_write_text(target, "héllo {{ world }}\n")
        assert target.read_text(encoding="utf-8") == "héllo {{ world }}\n"


class TestHashing:
    def test_sha256_bytes_known_vector(self):
        assert filesystem.sha256_bytes(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_sha256_file_matches_bytes(self, tmp_path):
        p = tmp_path / "f"
        p.write_bytes(b"omni-theme")
        assert filesystem.sha256_file(p) == filesystem.sha256_bytes(b"omni-theme")


class TestCleanDirectory:
    def test_removes_files_and_subtrees_keeps_root(self, tmp_path):
        root = tmp_path / "staging"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "x").write_text("x")
        (root / "top.txt").write_text("y")
        out = filesystem.clean_directory(root)
        assert out == root and list(root.iterdir()) == []

    def test_missing_directory_created(self, tmp_path):
        root = tmp_path / "fresh"
        assert filesystem.clean_directory(root).is_dir()


class TestPromoteDirectory:
    def test_fresh_install(self, tmp_path):
        new = tmp_path / "new"
        new.mkdir()
        (new / "a").write_text("a")
        backups = tmp_path / "backups"
        current = tmp_path / "live" / "current"

        out = filesystem.promote_directory(new, current, backup_root=backups)
        assert out == current
        assert (current / "a").read_text() == "a"
        assert not list(backups.iterdir())  # nothing to back up

    def test_swap_displaces_previous_into_backup(self, tmp_path):
        old = tmp_path / "old"
        old.mkdir()
        (old / "old.txt").write_text("old")

        new = tmp_path / "new"
        new.mkdir()
        (new / "new.txt").write_text("new")

        current = tmp_path / "live" / "current"
        current.parent.mkdir(parents=True)
        os.replace(old, current)

        backups = tmp_path / "backups"
        filesystem.promote_directory(new, current, backup_root=backups)

        assert (current / "new.txt").exists()
        slots = list(backups.iterdir())
        assert len(slots) == 1
        assert (slots[0] / "old.txt").read_text() == "old"

    def test_existing_current_without_backup_root_raises(self, tmp_path):
        current = tmp_path / "current"
        current.mkdir()
        new = tmp_path / "new"
        new.mkdir()
        with pytest.raises(FileExistsError):
            filesystem.promote_directory(new, current)

    def test_new_must_be_a_directory(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            filesystem.promote_directory(tmp_path / "absent", tmp_path / "cur")

    def test_backup_slots_are_unique_across_rapid_calls(self, tmp_path):
        current = tmp_path / "current"
        backups = tmp_path / "backups"
        for round_index in range(3):
            staging = tmp_path / f"stage{round_index}"
            staging.mkdir()
            filesystem.promote_directory(staging, current, backup_root=backups)
            # ensure `current` exists so the next promotion has something
            # to displace (the very first promotion installs fresh)
            current.mkdir(exist_ok=True)
        assert len(list(backups.iterdir())) == 2  # iterations 2 and 3 displace
