"""Unit tests for the GTK adapter (session 06).

Hermetic: detection runs against a sandbox config home, so GTK
detection is tested independently from any real desktop integration.
The KDE-sync strategy is verified against synthetic kdeglobals/colors.css
pairs (values mirrored from a live Plasma 6 machine).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import AdapterError

from adapters.gtk import direct as gtk_direct
from adapters.gtk import sync as gtk_sync
from adapters.gtk.adapter import (
    MODE_DIRECT,
    MODE_KDE_SYNC,
    MODE_OBSERVE,
    GtkAdapter,
)
from adapters.gtk.detection import detect_gtk

KCM = "/usr/bin/kcmshell6"


def _gtk_env(config_home: Path, *, versions=("gtk-3.0",), settings=""):
    config_home.mkdir(parents=True, exist_ok=True)
    for version in versions:
        d = config_home / version
        d.mkdir(parents=True, exist_ok=True)
        if settings:
            (d / "settings.ini").write_text(settings)
    return config_home


def _adapter(config_home: Path, *, kcmshell6: str | None = None,
             **kwargs) -> GtkAdapter:
    """Adapter pinned to the sandbox: never probes the host's PATH."""
    which = (
        (lambda name: kcmshell6 if name == "kcmshell6" else None)
        if kcmshell6 is not None
        else (lambda name: None)
    )
    return GtkAdapter(
        config_home=config_home,
        env={"XDG_CURRENT_DESKTOP": "KDE"},
        which=which,
        **kwargs,
    )


class TestDetectionIndependent:
    def test_no_gtk_anywhere(self, tmp_path):
        env = detect_gtk(env={"HOME": str(tmp_path)}, which=lambda n: None,
                         config_home=tmp_path / "cfg")
        assert not env.has_gtk()
        assert env.gtk_theme is None
        assert not env.kde_gtk_integration

    def test_settings_ini_parsed(self, tmp_path):
        ini = (
            "[Settings]\n"
            "gtk-theme-name=BreezeDark\n"
            "gtk-modules=colorreload-gtk-module:window-decorations-gtk-module\n"
        )
        cfg = _gtk_env(tmp_path / "cfg", settings=ini)
        env = detect_gtk(env={"XDG_CURRENT_DESKTOP": "KDE"},
                         which=lambda n: KCM if n == "kcmshell6" else None,
                         config_home=cfg)
        assert env.gtk_theme == "BreezeDark"
        assert env.colorreload_module_active
        assert env.kde_gtk_integration

    def test_kcmshell6_alone_is_enough_signal(self, tmp_path):
        cfg = _gtk_env(tmp_path / "cfg")
        env = detect_gtk(env={"XDG_CURRENT_DESKTOP": "KDE"},
                         which=lambda n: KCM if n == "kcmshell6" else None,
                         config_home=cfg)
        assert env.has_gtk("gtk-3.0")
        assert env.kde_gtk_integration  # via binary presence

    def test_detection_never_writes(self, tmp_path):
        cfg = _gtk_env(tmp_path / "cfg")
        before = sorted(str(p) for p in cfg.rglob("*"))
        detect_gtk(env={"XDG_CURRENT_DESKTOP": "KDE"},
                   which=lambda n: KCM if n == "kcmshell6" else None,
                   config_home=cfg)
        after = sorted(str(p) for p in cfg.rglob("*"))
        assert before == after


class TestCapability:
    def test_unsupported_without_gtk(self, tmp_path):
        cap = _adapter(tmp_path / "cfg").capability(None)
        assert cap.supported is False
        assert "no GTK" in cap.reason


class TestKdeSyncStrategy:
    @pytest.fixture
    def synced_config(self, tmp_path):
        """Config home with integration signals + matching KDE/GTK colors."""
        cfg = tmp_path / "cfg"
        _gtk_env(cfg, settings="[Settings]\ngtk-theme-name=breeze\n")
        # Values verified live on Plasma 6.7: scheme → kdeglobals → colors.css
        (cfg / "kdeglobals").write_text(
            "[Colors:Window]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
            "[Colors:View]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
            "[Colors:Selection]\nBackgroundNormal=69,144,175\nForegroundNormal=0,0,0\n"
        )
        (cfg / "gtk-3.0" / "colors.css").write_text(
            "@define-color theme_bg_color_breeze #14161c;\n"
            "@define-color theme_base_color_breeze #14161c;\n"
            "@define-color theme_fg_color_breeze #d6dae2;\n"
            "@define-color theme_text_color_breeze #d6dae2;\n"
            "@define-color theme_selected_bg_color_breeze #4590af;\n"
            "@define-color theme_selected_fg_color_breeze #000000;\n"
        )
        return cfg

    def _kde_sync_adapter(self, cfg: Path) -> GtkAdapter:
        # propagation_wait=0: sandbox has no kde-gtk-config daemon, so
        # no propagation window exists to wait out.
        return _adapter(cfg, kcmshell6=KCM, propagation_wait=0)

    def test_plan_selects_kde_sync_mode(self, synced_config, make_theme,
                                        context_factory):
        theme = load_theme(make_theme())
        plan = self._kde_sync_adapter(synced_config).plan(
            theme, context_factory(theme=theme))
        assert plan.mode == MODE_KDE_SYNC

    def test_apply_writes_nothing(self, synced_config, make_theme,
                                  context_factory):
        """Delegation is the mechanism: kde-sync mode must not touch files."""
        theme = load_theme(make_theme())
        ctx = context_factory(theme=theme)
        adapter = self._kde_sync_adapter(synced_config)
        before = {p: p.stat().st_mtime_ns for p in synced_config.rglob("*")}
        plan = adapter.plan(theme, ctx)
        result = adapter.apply(plan, ctx)

        assert result.applied is True and not result.errors
        for p in synced_config.rglob("*"):
            assert p in before  # no new files either

    def test_verify_passes_when_sync_is_intact(self, synced_config, make_theme,
                                               context_factory):
        theme = load_theme(make_theme())
        adapter = self._kde_sync_adapter(synced_config)
        plan = adapter.plan(theme, context_factory(theme=theme))
        result = adapter.verify(plan, context_factory(theme=theme))
        assert result.verified is True

    def test_verify_reports_drift(self, synced_config, make_theme,
                                  context_factory):
        # Break one propagated color.
        css = synced_config / "gtk-3.0" / "colors.css"
        css.write_text(css.read_text().replace("#14161c", "#ffffff"))
        theme = load_theme(make_theme())
        adapter = self._kde_sync_adapter(synced_config)
        plan = adapter.plan(theme, context_factory(theme=theme))
        result = adapter.verify(plan, context_factory(theme=theme))
        assert result.verified is False
        assert any("sync drift" in e for e in result.errors)

    def test_missing_colors_css_warns_but_verifies(self, synced_config,
                                                   make_theme, context_factory):
        (synced_config / "gtk-3.0" / "colors.css").unlink()
        theme = load_theme(make_theme())
        adapter = self._kde_sync_adapter(synced_config)
        plan = adapter.plan(theme, context_factory(theme=theme))
        assert any("colors.css" in w for w in plan.warnings)
        result = adapter.verify(plan, context_factory(theme=theme))
        assert result.verified is True  # absence ≠ broken propagation


class TestObserveMode:
    def test_without_integration_or_optin_nothing_is_written(
        self, tmp_path, make_theme, context_factory
    ):
        cfg = tmp_path / "cfg"
        _gtk_env(cfg)  # gtk dirs exist, no kcmshell6/module anywhere
        theme = load_theme(make_theme())
        ctx = context_factory(theme=theme)
        adapter = _adapter(cfg)
        plan = adapter.plan(theme, ctx)
        assert plan.mode == MODE_OBSERVE
        assert plan.warnings  # honest explanation present
        result = adapter.apply(plan, ctx)
        assert result.applied is True
        assert list((cfg / "gtk-3.0").iterdir()) == [] or all(
            p.name == "settings.ini" for p in (cfg / "gtk-3.0").iterdir()
        )


class TestDirectFallback:
    @pytest.fixture
    def plain_config(self, tmp_path):
        cfg = tmp_path / "cfg"
        _gtk_env(cfg)  # no integration signals
        return cfg

    def _run_direct(self, cfg, theme, context_factory):
        ctx = context_factory(theme=theme)
        adapter = _adapter(cfg, allow_direct=True)
        plan = adapter.plan(theme, ctx)
        applied = adapter.apply(plan, ctx)
        verified = adapter.verify(plan, ctx)
        return theme, ctx, plan, applied, verified

    def _fresh_theme(self, make_theme):
        return load_theme(make_theme())

    def test_requires_explicit_opt_in(self, plain_config, make_theme, context_factory):
        theme = load_theme(make_theme())
        plan = _adapter(plain_config).plan(theme, context_factory(theme=theme))
        assert plan.mode == MODE_OBSERVE
        assert not plan.direct_plans

    def test_creates_owned_file_with_markers(self, plain_config, make_theme,
                                             context_factory):
        _, _, _, applied, verified = self._run_direct(
            plain_config, self._fresh_theme(make_theme), context_factory
        )
        assert applied.applied and verified.verified
        target = plain_config / "gtk-3.0" / "gtk.css"
        text = target.read_text()
        assert gtk_direct.BEGIN_MARKER_PREFIX in text
        assert "owner = omni-theme-cachy" in text
        assert "source_generation" in text
        assert gtk_direct.END_MARKER in text
        assert "@define-color omni-bg #14161c;" in text

    def test_repeated_application_replaces_block_not_duplicates(
        self, plain_config, make_theme, context_factory
    ):
        _, ctx, _, _, _ = self._run_direct(plain_config, self._fresh_theme(make_theme), context_factory)
        target = plain_config / "gtk-3.0" / "gtk.css"
        first = target.read_text()
        theme2 = load_theme(make_theme(name="second"))
        adapter = _adapter(plain_config, allow_direct=True)
        plan = adapter.plan(theme2, ctx)
        adapter.apply(plan, ctx)
        second = target.read_text()
        assert second.count(gtk_direct.BEGIN_MARKER_PREFIX) == 1
        assert second != first

    def test_conflict_with_foreign_gtkcss_refused(self, plain_config, make_theme,
                                                  context_factory):
        target = plain_config / "gtk-3.0" / "gtk.css"
        user_css = "/* my precious custom css */\nbutton { all: unset; }\n"
        target.write_text(user_css)

        with pytest.raises(AdapterError, match="refusing"):
            self._run_direct(plain_config, self._fresh_theme(make_theme), context_factory)
        assert target.read_text() == user_css  # untouched

    def test_rollback_removes_file_we_created(
        self, plain_config, make_theme, context_factory
    ):
        theme, ctx, _, _, _ = self._run_direct(plain_config, self._fresh_theme(make_theme), context_factory)
        target = plain_config / "gtk-3.0" / "gtk.css"
        assert gtk_direct.BEGIN_MARKER_PREFIX in target.read_text()

        adapter = _adapter(plain_config, allow_direct=True)
        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert not target.exists()

    def test_rollback_restores_previous_bytes_of_preexisting_file(
        self, plain_config, make_theme, context_factory
    ):
        target = plain_config / "gtk-3.0" / "gtk.css"
        original = "#user {\n  color: red;\n}\n"
        target.write_text(original)

        force_adapter = _adapter(plain_config, allow_direct=True, direct_force=True)
        ctx = context_factory(theme=self._fresh_theme(make_theme))
        plan = force_adapter.plan(ctx.theme, ctx)
        applied = force_adapter.apply(plan, ctx)
        assert applied.applied
        assert target.read_text() != original

        adapter = _adapter(plain_config, allow_direct=True)
        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert target.read_text() == original

        # Post-rollback the file is user content again: a fresh direct
        # apply must conflict rather than silently mix in.
        with pytest.raises(AdapterError, match="refusing"):
            self._run_direct(plain_config, load_theme(make_theme(name="t2")),
                             context_factory)

    def test_ownership_uses_markers_not_readonly_bits(self, plain_config,
                                                      make_theme, context_factory):
        self._run_direct(plain_config, self._fresh_theme(make_theme), context_factory)
        target = plain_config / "gtk-3.0" / "gtk.css"
        # Never chmod 444 as an ownership strategy: file stays writable.
        assert target.stat().st_mode & 0o200

    def test_gtk4_gets_honest_limitation_warning(self, tmp_path, make_theme,
                                                 context_factory):
        cfg = tmp_path / "cfg"
        _gtk_env(cfg, versions=("gtk-3.0", "gtk-4.0"))
        theme = load_theme(make_theme())
        plan = _adapter(cfg, allow_direct=True).plan(theme, context_factory(theme=theme))
        assert any("libadwaita" in w or "GTK4" in w for w in plan.warnings)


class TestPropagationWindow:
    """kde-gtk-config rewrites colors.css *after* kdeglobals (observed
    ~0.2s behind on live Plasma 6.7); verify must poll inside the
    window instead of racing the daemon and failing a healthy sync."""

    @pytest.fixture
    def synced_config(self, tmp_path):
        cfg = tmp_path / "cfg"
        _gtk_env(cfg, settings="[Settings]\ngtk-theme-name=breeze\n")
        (cfg / "kdeglobals").write_text(
            "[Colors:Window]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
            "[Colors:View]\nBackgroundNormal=20,22,28\nForegroundNormal=214,218,226\n"
            "[Colors:Selection]\nBackgroundNormal=69,144,175\nForegroundNormal=0,0,0\n"
        )
        (cfg / "gtk-3.0" / "colors.css").write_text(
            "@define-color theme_bg_color_breeze #14161c;\n"
            "@define-color theme_base_color_breeze #14161c;\n"
            "@define-color theme_fg_color_breeze #d6dae2;\n"
            "@define-color theme_text_color_breeze #d6dae2;\n"
            "@define-color theme_selected_bg_color_breeze #4590af;\n"
            "@define-color theme_selected_fg_color_breeze #000000;\n"
        )
        return cfg

    def test_verify_polls_until_propagation_lands(self, synced_config,
                                                  make_theme,
                                                  context_factory):
        css = synced_config / "gtk-3.0" / "colors.css"
        stale = css.read_text().replace("#14161c", "#0a0a0a")
        css.write_text(stale)  # daemon has not caught up yet

        def daemon_lands(_delay: float) -> None:
            css.write_text(stale.replace("#0a0a0a", "#14161c"))

        theme = load_theme(make_theme())
        adapter = _adapter(synced_config, kcmshell6=KCM,
                           propagation_wait=2.0, sleep=daemon_lands)
        plan = adapter.plan(theme, context_factory(theme=theme))
        result = adapter.verify(plan, context_factory(theme=theme))
        assert result.verified is True
        assert not result.errors

    def test_persistent_drift_after_budget_is_an_error(self, synced_config,
                                                       make_theme,
                                                       context_factory):
        css = synced_config / "gtk-3.0" / "colors.css"
        css.write_text(css.read_text().replace("#14161c", "#0a0a0a"))

        theme = load_theme(make_theme())
        adapter = _adapter(synced_config, kcmshell6=KCM,
                           propagation_wait=0.0)
        plan = adapter.plan(theme, context_factory(theme=theme))
        result = adapter.verify(plan, context_factory(theme=theme))
        assert result.verified is False
        assert any("sync drift" in e for e in result.errors)


class TestSyncHelpers:
    PAIRS_TEXT_GLOBALS = (
        "[Colors:Window]\nBackgroundNormal=1,2,3\nForegroundNormal=214,218,226\n"
        "[Colors:View]\nBackgroundNormal=20,22,28\nForegroundNormal=4,5,6\n"
        "[Colors:Selection]\nBackgroundNormal=69,144,175\nForegroundNormal=0,0,0\n"
    )
    PAIRS_TEXT_CSS = (
        "@define-color theme_bg_color_breeze #010203;\n"
        "@define-color theme_base_color_breeze #14161c;\n"
        "@define-color theme_fg_color_breeze #d6dae2;\n"
        "@define-color theme_text_color_breeze #040506;\n"
        "@define-color theme_selected_bg_color_breeze #4590af;\n"
        "@define-color theme_selected_fg_color_breeze #000000;\n"
    )

    def test_verify_sync_clean(self):
        assert gtk_sync.verify_sync(self.PAIRS_TEXT_GLOBALS, self.PAIRS_TEXT_CSS) == []

    def test_verify_sync_detects_mismatch(self):
        problems = gtk_sync.verify_sync(
            self.PAIRS_TEXT_GLOBALS,
            self.PAIRS_TEXT_CSS.replace("#040506", "#999999"),
        )
        assert len(problems) == 1 and "drift" in problems[0]

    def test_rgb_function_values_accepted(self):
        problems = gtk_sync.verify_sync(
            self.PAIRS_TEXT_GLOBALS,
            self.PAIRS_TEXT_CSS.replace("#040506", "rgb(4,5,6)"),
        )
        assert problems == []


# imported late to keep the fixture sections readable
from core.theme_loader import load_theme  # noqa: E402
