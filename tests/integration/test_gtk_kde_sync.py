"""Engine-level integration tests for GTK ↔ KDE synchronization (session 11).

Hermetic: the "KDE side" of the chain is simulated by writing the files
KDE itself owns (``kdeglobals``, ``gtk-{3,4}.0/colors.css``) into a
sandbox config home, and kde-gtk-config's presence is injected via
``which``. The suite pins the engine-level contract:

* with KDE's sync mechanism present, activation delegates — Omni
  writes nothing into the config home and still verifies;
* sync drift after the propagation window is a hard, non-silent
  failure, whatever GTK theme the user picked;
* the non-Breeze boundary is the theme choice itself: reported in
  warnings, never overridden, never silently excused;
* without the integration, direct generation stays opt-in and the
  default (observe) writes nothing;
* kde-sync mode owns no files, so rollback reverts nothing in the
  config home.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.adapters import AdapterRegistry  # noqa: E402
from core.engine import ThemeEngine  # noqa: E402
from core.filesystem import sha256_file  # noqa: E402

from adapters.gtk import GtkAdapter  # noqa: E402

NO_WALLPAPER_TOML = '[theme]\nname = "T"\nid = "t"\nversion = 1\nmode = "dark"\n'

KCM = "/usr/bin/kcmshell6"

KDEGLOBALS = (
    "[Colors:Window]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
    "[Colors:View]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
    "[Colors:Selection]\nBackgroundNormal=69,144,175\nForegroundNormal=0,0,0\n"
)

COLORS_CSS = (
    "@define-color theme_bg_color_breeze #14161c;\n"
    "@define-color theme_base_color_breeze #14161c;\n"
    "@define-color theme_fg_color_breeze #d6dae2;\n"
    "@define-color theme_text_color_breeze #d6dae2;\n"
    "@define-color theme_selected_bg_color_breeze #4590af;\n"
    "@define-color theme_selected_fg_color_breeze #000000;\n"
)


def _write_sync_env(cfg: Path, *, gtk_theme: str, css_text: str = COLORS_CSS):
    for version in ("gtk-3.0", "gtk-4.0"):
        (cfg / version).mkdir(parents=True, exist_ok=True)
        (cfg / version / "settings.ini").write_text(
            f"[Settings]\ngtk-theme-name={gtk_theme}\n"
            "gtk-modules=colorreload-gtk-module\n"
        )
    (cfg / "kdeglobals").write_text(KDEGLOBALS)
    (cfg / "gtk-3.0" / "colors.css").write_text(css_text)


def _tree(cfg: Path) -> dict:
    return {p: sha256_file(p) if p.is_file() else "dir"
            for p in sorted(cfg.rglob("*"))}


def _engine(fake_home, cfg: Path) -> ThemeEngine:
    registry = AdapterRegistry()
    # propagation_wait=0: the sandbox has no kde-gtk-config daemon, so
    # there is no asynchronous propagation window to wait out.
    registry.register(GtkAdapter(
        config_home=cfg,
        env={"XDG_CURRENT_DESKTOP": "KDE"},
        which=lambda name: KCM if name == "kcmshell6" else None,
        propagation_wait=0,
    ))
    return ThemeEngine(
        themes_root=fake_home / "themes",
        templates_root=PROJECT_ROOT / "templates",
        state_root=fake_home / ".local" / "state" / "omni-theme",
        adapters=registry,
    )


def _gtk_result(outcome):
    return next(r for r in outcome.adapter_results if r.adapter_id == "gtk")


class TestKdeSyncDelegation:
    def test_activation_writes_nothing_and_verifies(self, fake_home,
                                                    make_theme):
        cfg = fake_home / ".config"
        _write_sync_env(cfg, gtk_theme="Breeze")
        before = _tree(cfg)
        eng = _engine(fake_home, cfg)

        outcome = eng.apply(make_theme(name="first",
                                       theme_toml=NO_WALLPAPER_TOML))

        assert outcome.ok, outcome.to_dict()
        result = _gtk_result(outcome)
        assert result.applied is True
        assert result.verified is True
        assert not result.errors
        assert _tree(cfg) == before  # Omni touched nothing KDE owns

    def test_sync_drift_is_never_silent(self, fake_home, make_theme):
        cfg = fake_home / ".config"
        _write_sync_env(cfg, gtk_theme="Breeze")
        eng = _engine(fake_home, cfg)
        assert eng.apply(make_theme(
            name="first", theme_toml=NO_WALLPAPER_TOML,
        )).ok

        # KDE's propagation broke between activations: colors.css no
        # longer matches kdeglobals.
        css = cfg / "gtk-3.0" / "colors.css"
        css.write_text(COLORS_CSS.replace("#14161c", "#0a0a0a"))

        outcome = eng.apply(make_theme(
            name="second", theme_toml=NO_WALLPAPER_TOML,
            colors={"accent": "#101010"},
        ))

        # The engine does not stay silent: adapter verify errors are
        # loud in the outcome (DEGRADED status + adapter error list).
        assert outcome.status == "DEGRADED"
        gtk_result = _gtk_result(outcome)
        assert gtk_result.verified is False
        assert any("sync drift" in e for e in gtk_result.errors)

    def test_repeat_activation_is_idempotent_for_kde_files(
        self, fake_home, make_theme,
    ):
        cfg = fake_home / ".config"
        _write_sync_env(cfg, gtk_theme="Breeze")
        eng = _engine(fake_home, cfg)
        assert eng.apply(make_theme(
            name="first", theme_toml=NO_WALLPAPER_TOML,
        )).ok
        before = _tree(cfg)

        outcome = eng.apply(make_theme(
            name="second", theme_toml=NO_WALLPAPER_TOML,
            colors={"accent": "#202020"},
        ))

        assert outcome.ok
        assert _tree(cfg) == before


class TestNonBreezeBoundary:
    def test_drift_is_not_excused_by_a_non_breeze_theme(
        self, fake_home, make_theme,
    ):
        """Sandbox has no daemon: colors.css stays stale, so the
        activation reports drift loudly no matter which GTK theme the
        user picked — Omni never silently excuses a broken chain."""
        cfg = fake_home / ".config"
        _write_sync_env(
            cfg, gtk_theme="WhiteSur-Light",
            css_text=COLORS_CSS.replace("#14161c", "#fdfdfd"),
        )
        eng = _engine(fake_home, cfg)

        outcome = eng.apply(make_theme(name="first",
                                       theme_toml=NO_WALLPAPER_TOML))

        assert outcome.status == "DEGRADED"
        result = _gtk_result(outcome)
        assert result.verified is False
        assert any("sync drift" in e for e in result.errors)
        # the boundary warning is recorded alongside the failure, and
        # the user's theme choice is untouched
        assert any("not" in w and "Breeze" in w for w in result.warnings)
        assert "WhiteSur-Light" in (
            cfg / "gtk-3.0" / "settings.ini"
        ).read_text()

    def test_plan_warns_about_the_boundary(self, tmp_path, make_theme,
                                           context_factory):
        cfg = tmp_path / "cfg"
        _write_sync_env(cfg, gtk_theme="WhiteSur-Light")
        ctx = context_factory(theme=make_theme())
        adapter = GtkAdapter(
            config_home=cfg,
            env={"XDG_CURRENT_DESKTOP": "KDE"},
            which=lambda name: KCM if name == "kcmshell6" else None,
            propagation_wait=0,
        )
        plan = adapter.plan(ctx.theme, ctx)
        assert any("not" in w and "Breeze" in w for w in plan.warnings)


class TestDirectDisabledByDefault:
    def test_observe_mode_through_engine(self, fake_home, make_theme):
        cfg = fake_home / ".config"
        (cfg / "gtk-3.0").mkdir(parents=True)
        eng = _engine(fake_home, cfg)

        outcome = eng.apply(make_theme(name="first",
                                       theme_toml=NO_WALLPAPER_TOML))

        assert outcome.ok
        result = _gtk_result(outcome)
        assert result.applied is True
        assert result.verified is True
        assert result.warnings  # honest explanation recorded
        assert not (cfg / "gtk-3.0" / "gtk.css").exists()
        assert not (cfg / "kdeglobals").exists()

    def test_no_gtk_at_all_is_skipped_not_fatal(self, fake_home, make_theme):
        cfg = fake_home / ".config"
        eng = _engine(fake_home, cfg)

        outcome = eng.apply(make_theme(name="first",
                                       theme_toml=NO_WALLPAPER_TOML))

        assert outcome.ok
        result = _gtk_result(outcome)
        assert result.attempted is False
        caps = {c.id: c for c in outcome.capabilities}
        assert caps["gtk"].supported is False


class TestRollbackOwnsNothing:
    def test_kde_files_survive_rollback_untouched(self, fake_home,
                                                  make_theme):
        cfg = fake_home / ".config"
        _write_sync_env(cfg, gtk_theme="Breeze")
        before = _tree(cfg)
        eng = _engine(fake_home, cfg)
        assert eng.apply(make_theme(
            name="first", theme_toml=NO_WALLPAPER_TOML,
        )).ok
        assert eng.apply(make_theme(
            name="second", theme_toml=NO_WALLPAPER_TOML,
            colors={"accent": "#303030"},
        )).ok

        rolled = eng.rollback()

        assert rolled.status == "ROLLED_BACK", rolled.to_dict()
        assert _tree(cfg) == before
        gtk_rolled = next(
            r for r in rolled.adapter_results if r.adapter_id == "gtk"
        )
        assert gtk_rolled.rolled_back is True
        assert any("owns no files" in w for w in gtk_rolled.warnings)
