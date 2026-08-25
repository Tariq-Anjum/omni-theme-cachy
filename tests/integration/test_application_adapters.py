"""End-to-end application-adapter integration tests (hermetic).

No live desktop required: every adapter is wired to sandboxed config
and data homes, and the KDE slot is deliberately registered *without*
its native tools so the suite also proves that unsupported adapters
are skipped-and-reported rather than failing the activation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.adapters import AdapterCapability, AdapterRegistry  # noqa: E402
from core.engine import ThemeEngine  # noqa: E402

from adapters.gtk import GtkAdapter  # noqa: E402
from adapters.konsole import KonsoleAdapter  # noqa: E402
from adapters.vscode import COLOR_CUSTOMIZATIONS_KEY, VscodeAdapter  # noqa: E402
from adapters.vscode import jsonc as vjson  # noqa: E402

# Fixture themes skip wallpapers: this suite exercises application
# adapters, not wallpaper plumbing.
NO_WALLPAPER_TOML = '[theme]\nname = "Test"\nid = "test"\nversion = 1\nmode = "dark"\n'


def _theme_dir(make_theme, name, **kwargs):
    return make_theme(name=name, theme_toml=NO_WALLPAPER_TOML, **kwargs)


class AlwaysUnsupportedKde:
    """Stand-in proving 'unsupported ≠ failure' inside the pipeline."""

    id = "kde"

    def capability(self, context):
        return AdapterCapability(id=self.id, supported=False,
                                 reason="plasma tools hidden in this sandbox")

    def plan(self, resolved_theme, context): ...

    def render(self, resolved_theme, staging, context): ...

    def apply(self, plan, context):
        from core.adapters import AdapterResult
        return AdapterResult(adapter_id=self.id)

    def verify(self, plan, context):
        from core.adapters import AdapterResult
        return AdapterResult(adapter_id=self.id)

    def rollback(self, previous_state, context):
        from core.adapters import AdapterResult
        return AdapterResult(adapter_id=self.id, rolled_back=True)


@pytest.fixture
def app_homes(fake_home):
    cfg = fake_home / ".config"
    data = fake_home / ".local" / "share"
    user_dir = cfg / "Code" / "User"
    user_dir.mkdir(parents=True)
    profiles_dir = data / "konsole"
    profiles_dir.mkdir(parents=True)
    (cfg / "gtk-3.0").mkdir()
    (cfg / "konsolerc").write_text("[Desktop Entry]\nDefaultProfile=ZSH.profile\n")
    (profiles_dir / "ZSH.profile").write_text("[General]\nCommand=/bin/zsh\n")
    return cfg, data


@pytest.fixture
def engine(fake_home, app_homes, make_theme, context_factory):
    cfg, data = app_homes
    registry = AdapterRegistry()
    registry.register(AlwaysUnsupportedKde())
    registry.register(GtkAdapter(config_home=cfg))
    registry.register(VscodeAdapter(config_home=cfg))
    registry.register(KonsoleAdapter(
        env={"HOME": str(fake_home)},
        which=lambda name: None,
        config_home=cfg,
        data_home=data,
    ))
    eng = ThemeEngine(
        themes_root=fake_home / "themes",
        templates_root=PROJECT_ROOT / "templates",
        state_root=fake_home / ".local" / "state" / "omni-theme",
        adapters=registry,
    )
    return eng


class TestFullActivation:
    def test_activation_succeeds_with_mixed_capabilities(self, engine, app_homes,
                                                         make_theme):
        cfg, data = app_homes
        outcome = engine.apply(_theme_dir(make_theme, "default"))

        assert outcome.ok, outcome.to_dict()
        caps = {c.id: c for c in outcome.capabilities}
        assert caps["kde"].supported is False  # reported, not fatal
        results = {r.adapter_id: r for r in outcome.adapter_results}
        assert results["kde"].attempted is False  # skipped

        # VS Code got colors without losing anything else
        settings = cfg / "Code" / "User" / "settings.json"
        parsed = vjson.loads(settings.read_text())
        assert parsed[COLOR_CUSTOMIZATIONS_KEY]["editor.background"] == "#14161c"

        # Konsole scheme installed and profile wired
        scheme = data / "konsole" / "OmniTheme.colorscheme"
        assert "[Background]" in scheme.read_text()
        profile = (data / "konsole" / "ZSH.profile").read_text()
        assert "ColorScheme=OmniTheme" in profile

        # GTK ran in observe mode (no integration signals in sandbox):
        # no direct writes happened, honest warning recorded instead
        assert list((cfg / "gtk-3.0").iterdir()) == []
        gtk_result = results["gtk"]
        assert gtk_result.applied is True

    def test_state_records_adapter_summary(self, engine, make_theme):
        outcome = engine.apply(_theme_dir(make_theme, "default"))
        assert outcome.ok
        summary = engine.status().adapters
        assert set(summary) == {"kde", "gtk", "vscode", "konsole"}
        assert summary["vscode"]["applied"] is True
        assert summary["kde"]["supported"] is False


class TestDryRunSafety:
    def test_dry_run_writes_nothing_to_applications(self, engine, app_homes,
                                                    make_theme):
        cfg, data = app_homes
        before_cfg = sorted(str(p) for p in cfg.rglob("*"))
        outcome = engine.apply(_theme_dir(make_theme, "default"), dry_run=True)

        assert outcome.status == "DRY_RUN"
        assert {c.id for c in outcome.capabilities} >= {"gtk", "vscode", "konsole"}
        after_cfg = sorted(str(p) for p in cfg.rglob("*"))
        assert before_cfg == after_cfg
        assert not (data / "konsole" / "OmniTheme.colorscheme").exists()


class TestRollbackThroughEngine:
    def test_rollback_restores_application_state(self, engine, app_homes,
                                                 make_theme):
        cfg, data = app_homes
        profile = data / "konsole" / "ZSH.profile"
        settings_file = cfg / "Code" / "User" / "settings.json"
        original_profile = profile.read_text()

        # Two themes with genuinely different palettes: identical content
        # would hit the engine's idempotent short-circuit and leave no
        # previous generation to roll back to.
        assert engine.apply(_theme_dir(
            make_theme, "first",
            colors={"accent": "#101010"},
        )).ok
        assert "ColorScheme=OmniTheme" in profile.read_text()

        outcome2 = engine.apply(_theme_dir(
            make_theme, "second",
            colors={"accent": "#202020"},
        ))
        assert outcome2.ok

        rolled = engine.rollback()
        assert rolled.status == "ROLLED_BACK", rolled.to_dict()

        # konsole profile key reverted to its pre-Omni bytes
        assert profile.read_text() == original_profile
        # our generated scheme removed (we created it)
        assert not (data / "konsole" / "OmniTheme.colorscheme").exists()


class TestUnsupportedOnly:
    def test_registry_of_only_unsupported_still_verifies(self, fake_home,
                                                         make_theme):
        registry = AdapterRegistry()
        registry.register(AlwaysUnsupportedKde())
        eng = ThemeEngine(
            themes_root=fake_home / "themes",
            templates_root=PROJECT_ROOT / "templates",
            state_root=fake_home / ".local" / "state" / "omni-theme",
            adapters=registry,
        )
        outcome = eng.apply(_theme_dir(make_theme, "solo"))
        assert outcome.status == "VERIFIED"
        assert outcome.adapter_results[0].supported is False
        assert outcome.adapter_results[0].failed is False
