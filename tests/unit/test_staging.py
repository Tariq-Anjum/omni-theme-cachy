"""Unit tests for core.staging: pipeline, manifests, conflicts (session 03)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from core import filesystem
from core.errors import ManifestError, StagingError
from core.staging import (
    Manifest,
    detect_conflicts,
    load_manifest,
    stage_theme,
    write_manifest,
)
from tests.conftest import FULL_PALETTE

REGISTRY_TWO = """
[[template]]
adapter = "kde-colorscheme"

[template.source]
path = "kde/test.colors.tpl"

[template.target]
path = "~/.local/share/color-schemes/Test.colors"

[[template]]
[template.source]
path = "term/foot.ini.tpl"

[template.target]
path = "~/.config/foot/foot.ini"
"""


@pytest.fixture
def engine(tmp_path, make_theme):
    """Offline engine environment: templates, registry, base theme."""
    templates = tmp_path / "templates"
    (templates / "kde").mkdir(parents=True)
    (templates / "term").mkdir(parents=True)
    (templates / "kde" / "test.colors.tpl").write_text(
        "# rendered by omni-theme\n"
        "Accent={{ accent }}\n"
        "Mixed={{ mix accent background 20% }}\n"
    )
    (templates / "term" / "foot.ini.tpl").write_text(
        "foreground={{ foreground }}\ncursor={{ color7_strip }}\n"
    )
    registry = templates / "targets.toml"
    registry.write_text(REGISTRY_TWO)
    return {
        "registry": registry,
        "templates_root": templates,
        "theme": make_theme(),
        "user_templates": Path("~/.config/omni-theme/templates"),
    }


def _stage(engine, **overrides):
    kwargs = dict(
        registry_path=engine["registry"],
        templates_root=engine["templates_root"],
    )
    kwargs.update(overrides)
    return stage_theme(engine["theme"], **kwargs)


class TestPipeline:
    def test_renders_all_targets_into_clean_staging(self, engine, fake_home):
        result = _stage(engine)
        staging = result.staging_dir
        expected_root = fake_home / ".local" / "state" / "omni-theme" / "staging"
        assert staging == expected_root

        colors = (staging / "kde" / "test.colors").read_text()
        assert f"Accent={FULL_PALETTE['accent']}" in colors
        assert "{{" not in colors  # no template markers leak

        foot = (staging / "term" / "foot.ini").read_text()
        assert foot == f"foreground={FULL_PALETTE['foreground']}\ncursor=c5cbd6\n"

        names = {f.name for f in result.files}
        assert names == {"kde/test.colors.tpl", "term/foot.ini.tpl"}
        assert result.ownership == "base"

    def test_stale_files_are_removed_between_runs(self, engine):
        first = _stage(engine)
        junk = first.staging_dir / "junk.txt"
        junk.write_text("leftover")
        second = _stage(engine)
        assert not junk.exists()
        assert second.staging_dir == first.staging_dir

    def test_nothing_touches_live_paths_or_current(self, engine, fake_home):
        _stage(engine)
        assert not (fake_home / ".local/share/color-schemes/Test.colors").exists()
        assert not (fake_home / ".config/foot/foot.ini").exists()
        assert not (fake_home / ".local/state/omni-theme/current").exists()

    def test_render_failure_names_template(self, engine):
        bad = engine["templates_root"] / "kde" / "broken.tpl"
        bad.write_text("oops={{ does_not_exist }}")
        engine["registry"].write_text(
            REGISTRY_TWO
            + '\n[[template]]\n[template.source]\npath = "kde/broken.tpl"\n'
            '[template.target]\npath = "~/broken"\n'
        )
        with pytest.raises(StagingError, match="kde/broken.tpl"):
            _stage(engine)

    def test_empty_render_refused(self, engine):
        blank = engine["templates_root"] / "term" / "blank.ini.tpl"
        blank.write_text("")
        engine["registry"].write_text(
            REGISTRY_TWO
            + '\n[[template]]\n[template.source]\npath = "term/blank.ini.tpl"\n'
            '[template.target]\npath = "~/blank"\n'
        )
        with pytest.raises(StagingError, match="empty"):
            _stage(engine)


class TestUserOverlayIntegration:
    def test_overlay_changes_output_and_ownership(self, engine, fake_home):
        overlay = fake_home / ".config/omni-theme/themes/test"
        overlay.mkdir(parents=True)
        (overlay / "colors.toml").write_text('accent = "#123456"\n')

        result = _stage(engine, user_theme_overlay_dir=overlay)
        colors = (result.staging_dir / "kde" / "test.colors").read_text()
        assert "Accent=#123456" in colors
        assert result.ownership == "user-overlay"

        manifest = load_manifest(result.manifest_path)
        assert manifest.ownership == "user-overlay"

    def test_without_overlay_manifest_is_base(self, engine):
        manifest = load_manifest(_stage(engine).manifest_path)
        assert manifest.ownership == "base"


class TestTemplatePrecedenceIntegration:
    def test_user_template_overrides_builtin(self, engine, fake_home):
        user_tpl = fake_home / ".config/omni-theme/templates/kde/test.colors.tpl"
        user_tpl.parent.mkdir(parents=True)
        user_tpl.write_text("USER-WINS={{ selection }}\n")

        result = _stage(engine, user_templates_dir=user_tpl.parents[1])
        staged = result.staging_dir / "kde" / "test.colors"
        assert staged.read_text() == f"USER-WINS={FULL_PALETTE['selection']}\n"

        entry = next(f for f in result.files if f.name == "kde/test.colors.tpl")
        assert entry.origin == "user"
        assert entry.source == user_tpl

        # untouched template still resolves to built-in
        foot = next(f for f in result.files if f.name == "term/foot.ini.tpl")
        assert foot.origin == "builtin"

    def test_theme_specific_beats_builtin(self, engine, make_theme):
        custom = make_theme(name="custom")
        tpl_dir = custom / "templates" / "kde"
        tpl_dir.mkdir(parents=True)
        (tpl_dir / "test.colors.tpl").write_text("THEME-SPECIFIC\n")

        result = stage_theme(
            custom,
            registry_path=engine["registry"],
            templates_root=engine["templates_root"],
        )
        entry = next(f for f in result.files if f.name == "kde/test.colors.tpl")
        assert entry.origin == "theme"
        assert (result.staging_dir / "kde" / "test.colors").read_text() == (
            "THEME-SPECIFIC\n"
        )


class TestManifest:
    def test_manifest_structure(self, engine, fake_home):
        result = _stage(engine)
        raw = json.loads(result.manifest_path.read_text())
        assert raw["version"] == 1
        assert raw["theme"] == {"name": "Test", "id": "test", "version": 1, "mode": "dark"}
        assert raw["ownership"] == "base"
        assert raw["theme_source"] == str(engine["theme"])
        # ISO-8601 UTC timestamp
        datetime.fromisoformat(raw["timestamp"])

        files = {f["name"]: f for f in raw["files"]}
        colors_entry = files["kde/test.colors.tpl"]
        assert colors_entry["adapter"] == "kde-colorscheme"
        assert colors_entry["origin"] == "builtin"
        assert colors_entry["target"] == str(
            (fake_home / ".local/share/color-schemes/Test.colors")
        )
        staged_bytes = (result.staging_dir / "kde" / "test.colors").read_bytes()
        assert colors_entry["hash"] == filesystem.sha256_bytes(staged_bytes)
        assert set(colors_entry) >= {
            "name", "source", "origin", "target", "adapter", "hash", "staged",
        }

    def test_round_trip_through_load_manifest(self, engine):
        result = _stage(engine)
        loaded = load_manifest(result.manifest_path)
        assert loaded.theme_name == "Test"
        assert loaded.theme_id == "test"
        assert loaded.mode == "dark"
        assert len(loaded.files) == 2
        by_name = {f.name: f for f in loaded.files}
        colors = by_name["kde/test.colors.tpl"]
        assert colors.adapter == "kde-colorscheme"
        assert colors.hash == filesystem.sha256_file(result.staging_dir / "kde" / "test.colors")

    def test_write_and_load_manual_manifest(self, tmp_path):
        manifest = Manifest(
            theme_name="N", theme_id="n", theme_version=2, mode="light",
            theme_source=tmp_path, timestamp="2026-08-24T00:00:00+00:00",
            ownership="base",
            files=(),
        )
        path = write_manifest(manifest, tmp_path / "manifest.json")
        loaded = load_manifest(path)
        assert loaded.theme_name == "N"
        assert loaded.theme_version == 2
        assert loaded.files == ()

    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(ManifestError, match="missing manifest"):
            load_manifest(tmp_path / "absent.json")

    def test_corrupt_json_raises(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text("{not json")
        with pytest.raises(ManifestError, match="invalid JSON"):
            load_manifest(p)

    def test_wrong_version_raises(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps({"version": 99}))
        with pytest.raises(ManifestError, match="unsupported manifest version"):
            load_manifest(p)

    def test_entry_with_missing_keys_raises(self, tmp_path):
        p = tmp_path / "manifest.json"
        p.write_text(json.dumps({
            "version": 1,
            "theme": {"name": "x", "id": "x", "version": 1, "mode": "dark"},
            "files": [{"name": "a"}],
        }))
        with pytest.raises(ManifestError, match="missing keys"):
            load_manifest(p)


class TestConflictDetection:
    def test_fresh_install_has_no_conflicts(self, engine):
        result = _stage(engine)
        assert detect_conflicts(load_manifest(result.manifest_path)) == []

    def test_unchanged_live_files_are_safe(self, engine, fake_home):
        result = _stage(engine)
        manifest = load_manifest(result.manifest_path)
        for f in manifest.files:
            target = Path(f.target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((result.staging_dir / f.staged).read_bytes())
        assert detect_conflicts(manifest) == []

    def test_modified_live_file_is_reported(self, engine, fake_home):
        result = _stage(engine)
        manifest = load_manifest(result.manifest_path)
        target = Path(manifest.files[0].target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# hand-edited by the user\n")

        conflicts = detect_conflicts(manifest)
        assert len(conflicts) == 1
        assert conflicts[0].target == target
        assert conflicts[0].managed_hash != conflicts[0].actual_hash
        assert conflicts[0].actual_hash is not None

    def test_vanished_live_file_is_not_a_conflict(self, engine, fake_home):
        result = _stage(engine)
        manifest = load_manifest(result.manifest_path)
        # create only the first target; leave the second absent
        f0 = manifest.files[0]
        target = Path(f0.target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((result.staging_dir / f0.staged).read_bytes())
        assert detect_conflicts(manifest) == []

    @pytest.mark.skipif(os.geteuid() == 0, reason="chmod 000 cannot stop root")
    def test_unreadable_live_file_counts_as_conflict(self, engine, fake_home):
        result = _stage(engine)
        manifest = load_manifest(result.manifest_path)
        target = Path(manifest.files[0].target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("data")
        os.chmod(target, 0o000)
        try:
            conflicts = detect_conflicts(manifest)
        finally:
            os.chmod(target, 0o644)
        assert len(conflicts) == 1
        assert conflicts[0].actual_hash is None
