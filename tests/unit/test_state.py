"""Unit tests for core.state: state.json, generations, atomic pointers, conflicts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core import filesystem, state
from core.errors import StateError
from core.staging import Manifest, ManifestFileEntry, write_manifest


@pytest.fixture
def root(tmp_path):
    return tmp_path / "state-root"


def _manifest(tmp_path: Path, *, accent: str = "#4f9eea", target: str = "~/x.conf") -> Manifest:
    """One-entry manifest whose staged content is deterministic."""
    content = f"accent={accent}\n"
    entry = ManifestFileEntry(
        name="x/y.tpl",
        source="/templates/x.tpl",
        origin="builtin",
        target=str(Path(target).expanduser()),
        adapter=None,
        hash=filesystem.sha256_bytes(content.encode()),
        staged="x/y",
    )
    return Manifest(
        theme_name="N", theme_id="n", theme_version=1, mode="dark",
        theme_source=tmp_path, timestamp="2026-08-25T00:00:00+00:00",
        ownership="base",
        files=(entry,),
    )


class TestGenerationIds:
    def test_unique_across_many_calls(self):
        ids = {state.new_generation_id() for _ in range(500)}
        assert len(ids) == 500

    def test_shape_is_sortable(self):
        first = state.new_generation_id()
        second = state.new_generation_id()
        assert first < second  # timestamp+counter prefix ordering
        assert first.startswith("gen-")


class TestStateRoundTrip:
    def test_missing_file_reads_as_fresh_state(self, root):
        loaded = state.read_state(root)
        assert loaded.current_theme is None
        assert loaded.previous_theme is None
        assert loaded.current_generation is None
        assert loaded.managed_targets == ()

    def test_write_then_read_preserves_everything(self, root):
        st = state.RuntimeState(
            current_theme="alpha",
            previous_theme=None,
            activated_at="2026-08-25T10:00:00+00:00",
            current_generation="gen-a",
            previous_generation=None,
            managed_targets=(
                state.ManagedTarget(
                    target="/home/u/.config/foot/foot.ini",
                    hash="abc123",
                    name="term/foot.ini.tpl",
                    adapter=None,
                ),
            ),
            adapters={"kde": {"supported": True, "applied": True}},
        )
        state.write_state(root, st)
        raw = json.loads((root / "state.json").read_text())
        assert raw["schema_version"] == 1

        loaded = state.read_state(root)
        assert loaded == st

    def test_corrupt_json_raises(self, root):
        root.mkdir(parents=True)
        (root / "state.json").write_text("{nope")
        with pytest.raises(StateError, match="invalid JSON"):
            state.read_state(root)

    def test_wrong_schema_version_raises(self, root):
        root.mkdir(parents=True)
        (root / "state.json").write_text(json.dumps({"schema_version": 99}))
        with pytest.raises(StateError, match="unsupported state schema_version"):
            state.read_state(root)

    def test_managed_target_with_bad_types_raises(self, root):
        root.mkdir(parents=True)
        (root / "state.json").write_text(json.dumps({
            "schema_version": 1,
            "managed_targets": [{"target": 5}],
        }))
        with pytest.raises(StateError, match="managed_targets"):
            state.read_state(root)


class TestLayout:
    def test_ensure_layout_creates_subdirs_but_not_pointers(self, root):
        state.ensure_layout(root)
        for sub in ("generations", "staging", "backups"):
            assert (root / sub).is_dir()
        assert not (root / "current").exists()
        assert not (root / "previous").exists()

    def test_invalid_generation_ids_rejected(self, root):
        with pytest.raises(StateError):
            state.generation_dir(root, "../escape")
        with pytest.raises(StateError):
            state.generation_dir(root, "")
        with pytest.raises(StateError):
            state.generation_dir(root, "a/b")


class TestAtomicPointers:
    def test_switch_link_creates_relative_symlink(self, root):
        state.ensure_layout(root)
        gen = root / "generations" / "gen-1"
        gen.mkdir(parents=True)

        link = state.switch_link(root, "current", "gen-1")

        assert link.is_symlink()
        assert os.readlink(link) == "generations/gen-1"  # relative
        assert link.resolve() == gen.resolve()

    def test_switch_link_swap_is_clean(self, root):
        state.ensure_layout(root)
        for gid in ("gen-1", "gen-2"):
            (root / "generations" / gid).mkdir(parents=True)

        state.switch_link(root, "current", "gen-1")
        state.switch_link(root, "previous", "gen-1")
        state.switch_link(root, "current", "gen-2")

        assert state.link_target(root, "current") == "gen-2"
        assert state.link_target(root, "previous") == "gen-1"
        # temp siblings never linger
        assert not (root / ".current.new").exists()
        assert not (root / ".previous.new").exists()

    def test_switch_link_to_missing_generation_raises(self, root):
        state.ensure_layout(root)
        with pytest.raises(StateError, match="missing generation"):
            state.switch_link(root, "current", "ghost")

    def test_switch_link_refuses_real_directory(self, root):
        state.ensure_layout(root)
        (root / "generations" / "gen-1").mkdir(parents=True)
        (root / "current").mkdir()  # pre-generation layout leftover
        with pytest.raises(StateError, match="not a symlink"):
            state.switch_link(root, "current", "gen-1")


class TestPromotionAndRevert:
    def _prepare(self, root: Path) -> None:
        state.ensure_layout(root)
        for gid in ("gen-1", "gen-2"):
            (root / "generations" / gid).mkdir(exist_ok=True)

    def test_first_promotion_has_no_previous(self, root):
        self._prepare(root)
        outgoing = state.promote_generation(root, "gen-1")
        assert outgoing is None
        assert state.link_target(root, "current") == "gen-1"
        assert state.link_target(root, "previous") is None

    def test_second_promotion_displaces_previous(self, root):
        self._prepare(root)
        state.promote_generation(root, "gen-1")
        outgoing = state.promote_generation(root, "gen-2")
        assert outgoing == "gen-1"
        assert state.link_target(root, "current") == "gen-2"
        assert state.link_target(root, "previous") == "gen-1"

    def test_revert_to_prior_state_restores_pointer_pair(self, root):
        self._prepare(root)
        state.promote_generation(root, "gen-1")
        prior = state.RuntimeState(
            current_generation="gen-1", previous_generation=None,
        )
        state.promote_generation(root, "gen-2")

        state.revert_to_state(root, prior)

        assert state.link_target(root, "current") == "gen-1"
        assert state.link_target(root, "previous") is None

    def test_revert_to_empty_removes_links(self, root):
        self._prepare(root)
        state.promote_generation(root, "gen-1")

        state.revert_to_state(root, state.RuntimeState())

        assert not (root / "current").exists()
        assert not (root / "previous").exists()


class TestGenerationManifests:
    def test_load_generation_manifest(self, tmp_path, root):
        manifest = _manifest(tmp_path)
        gen = root / "generations" / "gen-m"
        gen.mkdir(parents=True)
        write_manifest(manifest, gen / "manifest.json")

        loaded = state.load_generation_manifest(root, "gen-m")
        assert loaded.theme_id == "n"

    def test_manifest_hash_map(self, tmp_path):
        manifest = _manifest(tmp_path)
        assert state.manifest_hash_map(manifest) == {"x/y.tpl": manifest.files[0].hash}


class TestManagedConflicts:
    def _state_with_target(self, tmp_path, target: Path, content_hash: str):
        return state.RuntimeState(
            managed_targets=(
                state.ManagedTarget(target=str(target), hash=content_hash),
            ),
        )

    def test_absent_target_is_safe(self, tmp_path):
        target = tmp_path / "absent.conf"
        manifest = _manifest(tmp_path, target=str(target))
        st = self._state_with_target(tmp_path, target, manifest.files[0].hash)
        assert state.inspect_managed_conflicts(st, manifest) == []

    def test_untracked_existing_target_conflicts(self, tmp_path):
        target = tmp_path / "user-file.conf"
        target.write_text("user content\n")
        manifest = _manifest(tmp_path, target=str(target))
        st = state.RuntimeState()

        conflicts = state.inspect_managed_conflicts(st, manifest)

        assert len(conflicts) == 1
        assert conflicts[0].managed_hash == ""  # engine never owned it
        assert conflicts[0].actual_hash == filesystem.sha256_file(target)

    def test_owned_and_unmodified_target_is_safe(self, tmp_path):
        target = tmp_path / "ours.conf"
        target.write_text("accent=#4f9eea\n")
        manifest = _manifest(tmp_path, target=str(target))
        st = self._state_with_target(
            tmp_path, target, filesystem.sha256_file(target)
        )
        assert state.inspect_managed_conflicts(st, manifest) == []

    def test_user_modified_owned_target_conflicts(self, tmp_path):
        target = tmp_path / "edited.conf"
        target.write_text("accent=#4f9eea\n")
        manifest = _manifest(tmp_path, target=str(target))
        st = self._state_with_target(tmp_path, target, "stale-written-hash")

        conflicts = state.inspect_managed_conflicts(st, manifest)

        assert len(conflicts) == 1
        assert conflicts[0].managed_hash == "stale-written-hash"

    @pytest.mark.skipif(os.geteuid() == 0, reason="chmod 000 cannot stop root")
    def test_unreadable_target_counts_as_conflict(self, tmp_path):
        target = tmp_path / "locked.conf"
        target.write_text("data\n")
        manifest = _manifest(tmp_path, target=str(target))
        st = self._state_with_target(tmp_path, target, manifest.files[0].hash)
        os.chmod(target, 0o000)
        try:
            conflicts = state.inspect_managed_conflicts(st, manifest)
        finally:
            os.chmod(target, 0o644)
        assert len(conflicts) == 1
        assert conflicts[0].actual_hash is None
