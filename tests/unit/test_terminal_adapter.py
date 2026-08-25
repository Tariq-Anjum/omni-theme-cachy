"""Unit tests for the Konsole terminal adapter (session 06).

Hermetic: konsole detection, the colorscheme model, profile surgery and
all contract phases run against sandboxed config/data homes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.errors import AdapterError
from core.theme_loader import load_theme

from adapters.konsole import colorscheme as kc
from adapters.konsole.adapter import (
    Journal,
    KonsoleAdapter,
    journal_path,
)
from adapters.konsole.detection import detect_konsole


def _install(cfg: Path, data: Path, *, default_profile="ZSH.profile",
             profile_text="[General]\nCommand=/bin/zsh\nName=ZSH\n"):
    """Lay out a Konsole home: konsolerc + <data>/konsole/<profile>."""
    cfg.mkdir(parents=True, exist_ok=True)
    profiles = data / "konsole"
    profiles.mkdir(parents=True, exist_ok=True)
    (cfg / "konsolerc").write_text(
        f"[Desktop Entry]\nDefaultProfile={default_profile}\n"
        if default_profile else ""
    )
    if default_profile:
        (profiles / default_profile).write_text(profile_text)
    return cfg, profiles


def _adapter(cfg: Path, data: Path) -> KonsoleAdapter:
    """Adapter pinned to sandbox dirs; never probes host PATH."""
    return KonsoleAdapter(
        env={"HOME": str(cfg.parent)},
        which=lambda name: "/usr/bin/konsole" if name == "konsole" else None,
        config_home=cfg,
        data_home=data,
    )


class TestDetection:
    def test_not_installed(self, tmp_path):
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        detected = detect_konsole(env={}, which=lambda n: None,
                                  config_home=cfg, data_home=tmp_path / "data")
        assert not detected.installed

    def test_default_profile_discovered(self, tmp_path):
        cfg = tmp_path / "cfg"
        data = tmp_path / "data"
        _install(cfg, data)
        detected = detect_konsole(env={}, which=lambda n: None,
                                  config_home=cfg, data_home=data)
        assert detected.default_profile == "ZSH.profile"
        assert detected.profile_path() == data / "konsole" / "ZSH.profile"

    def test_missing_profile_file_detected(self, tmp_path):
        cfg = tmp_path / "cfg"
        cfg.mkdir()
        data = tmp_path / "data"
        data.mkdir()
        (cfg / "konsolerc").write_text("[Desktop Entry]\nDefaultProfile=Gone.profile\n")
        detected = detect_konsole(env={}, which=lambda n: "/usr/bin/konsole",
                                  config_home=cfg, data_home=data)
        assert detected.default_profile == "Gone.profile"
        assert detected.profile_path() is None


class TestCapability:
    def test_unsupported_when_konsole_absent(self, tmp_path):
        cfg = tmp_path / "cfg"; cfg.mkdir()
        data = tmp_path / "data"; data.mkdir()
        bare = KonsoleAdapter(env={}, which=lambda n: None,
                              config_home=cfg, data_home=data)
        cap = bare.capability(None)
        assert cap.supported is False and "not installed" in cap.reason

    def test_unsupported_without_default_profile(self, tmp_path):
        cfg = tmp_path / "cfg"
        data = tmp_path / "data"
        _install(cfg, data, default_profile=None)
        cap = _adapter(cfg, data).capability(None)
        assert cap.supported is False
        assert "DefaultProfile" in cap.reason

    def test_unsupported_when_profile_file_missing(self, tmp_path):
        cfg = tmp_path / "cfg"
        data = tmp_path / "data"
        _install(cfg, data, default_profile="Gone.profile")
        (data / "konsole" / "Gone.profile").unlink()
        cap = _adapter(cfg, data).capability(None)
        assert cap.supported is False and "not found" in cap.reason

    def test_supported_with_real_profile(self, tmp_path):
        cfg = tmp_path / "cfg"
        data = tmp_path / "data"
        _install(cfg, data)
        assert _adapter(cfg, data).capability(None).supported is True


class TestColorschemeModel:
    def test_ansi_ramp_mapping(self, palette_dict):
        text = kc.render_colorscheme(palette_dict)
        entries = kc.parse_colorscheme(text)

        def color(section):
            return tuple(int(v) for v in entries[(section, "Color")].split(","))

        from core.color import hex_to_rgb
        assert color("Background") == hex_to_rgb(palette_dict["background"])
        assert color("Foreground") == hex_to_rgb(palette_dict["foreground"])
        for i in range(8):
            assert color(f"Color{i}") == hex_to_rgb(palette_dict[f"color{i}"])
            # Konsole's intense sections carry the classic bright ramp.
            assert color(f"Color{i}Intense") == hex_to_rgb(palette_dict[f"color{i + 8}"])

    def test_general_metadata(self, palette_dict):
        entries = kc.parse_colorscheme(kc.render_colorscheme(palette_dict))
        assert entries[("General", "Description")] == "Omni Theme"
        assert entries[("General", "Opacity")] == "1"


class TestApplyVerifyRollback:
    @pytest.fixture
    def world(self, tmp_path, make_theme):
        cfg = tmp_path / "cfg"
        data = tmp_path / "data"
        _install(cfg, data)
        theme = load_theme(make_theme())
        ctx = type("Ctx", (), {"state_root": tmp_path / "state"})()
        return cfg, data, theme, ctx

    def _run(self, adapter, theme, ctx):
        plan = adapter.plan(theme, ctx)
        applied = adapter.apply(plan, ctx)
        verified = adapter.verify(plan, ctx)
        return plan, applied, verified

    def test_apply_writes_scheme_and_wires_profile(self, world):
        cfg, data, theme, ctx = world
        adapter = _adapter(cfg, data)
        plan, applied, verified = self._run(adapter, theme, ctx)

        assert applied.applied is True
        assert verified.verified is True
        scheme = data / "konsole" / kc.SCHEME_FILENAME
        assert scheme.is_file()
        assert scheme.read_text() == plan.rendered_scheme

        profile_text = (data / "konsole" / "ZSH.profile").read_text()
        assert "[Appearance]" in profile_text
        assert f"ColorScheme={kc.SCHEME_ID}" in profile_text
        # untouched sibling keys survive byte-for-byte
        assert "Command=/bin/zsh" in profile_text
        assert "Name=ZSH" in profile_text

    def test_repeated_application_is_idempotent(self, world):
        cfg, data, theme, ctx = world
        adapter = _adapter(cfg, data)
        first_plan, _, first_verify = self._run(adapter, theme, ctx)
        scheme = data / "konsole" / kc.SCHEME_FILENAME
        first_bytes = scheme.read_bytes()
        profile_first = (data / "konsole" / "ZSH.profile").read_bytes()

        second_plan, second_applied, second_verified = self._run(adapter, theme, ctx)
        assert second_applied.applied and second_verified.verified
        assert scheme.read_bytes() == first_bytes
        assert (data / "konsole" / "ZSH.profile").read_bytes() == profile_first

    def test_rollback_restores_profile_and_removes_created_scheme(self, world):
        cfg, data, theme, ctx = world
        adapter = _adapter(cfg, data)
        self._run(adapter, theme, ctx)
        assert (data / "konsole" / kc.SCHEME_FILENAME).exists()

        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert not (data / "konsole" / kc.SCHEME_FILENAME).exists()
        profile_text = (data / "konsole" / "ZSH.profile").read_text()
        assert "ColorScheme" not in profile_text
        assert "[Appearance]" not in profile_text
        assert "Command=/bin/zsh" in profile_text

    def test_rollback_restores_previous_colorscheme_value(self, world):
        cfg, data, theme, ctx = world
        original = "[General]\nCommand=/bin/zsh\n\n[Appearance]\nColorScheme=BreezeDark\n"
        (data / "konsole" / "ZSH.profile").write_text(original)

        adapter = _adapter(cfg, data)
        self._run(adapter, theme, ctx)
        assert "OmniTheme" in (data / "konsole" / "ZSH.profile").read_text()

        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert "ColorScheme=BreezeDark" in (data / "konsole" / "ZSH.profile").read_text()

    def test_rollback_keeps_preexisting_scheme_file_content(self, world):
        cfg, data, theme, ctx = world
        user_scheme = "[General]\nDescription=User's own OmniTheme\nOpacity=0.9\n"
        (data / "konsole" / kc.SCHEME_FILENAME).write_text(user_scheme)

        force_adapter = KonsoleAdapter(
            env={}, which=lambda n: "/usr/bin/konsole" if n == "konsole" else None,
            config_home=cfg, data_home=data,
        )
        plan = force_adapter.plan(theme, ctx)
        force_adapter.apply(plan, ctx)  # overwrites owned-path content

        result = force_adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert (data / "konsole" / kc.SCHEME_FILENAME).read_text() == user_scheme

    def test_rollback_without_journal_succeeds_with_warning(self, world):
        cfg, data, theme, ctx = world
        result = _adapter(cfg, data).rollback(None, ctx)
        assert result.rolled_back is True
        assert any("journal" in w for w in result.warnings)


class TestJournalPersistence:
    def test_round_trip(self, tmp_path):
        jp = tmp_path / "adapters" / "konsole.json"
        j = Journal(path=jp, scheme_existed=True, profile_path="/x/y")
        j.save()
        loaded = Journal.load(jp)
        assert loaded.scheme_existed is True
        assert loaded.profile_path == "/x/y"

    def test_corrupt_journal_recovers_empty(self, tmp_path):
        jp = tmp_path / "adapters" / "konsole.json"
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text("{bogus")
        assert Journal.load(jp).profile_path is None
