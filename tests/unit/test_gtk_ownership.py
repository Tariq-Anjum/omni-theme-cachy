"""Ownership-model tests for the GTK adapter (session 11).

Pin down *who owns which GTK file* in every mode:

* ``kdeglobals`` and ``gtk-{3,4}.0/colors.css`` are KDE-owned — Omni
  never creates, modifies, or deletes them in any mode;
* ``gtk-3.0/gtk.css`` is only ever touched in direct mode, only behind
  an explicit opt-in, and only as a marker-wrapped managed block with
  journalled rollback — never via read-only permission bits;
* user content outside the markers is an ownership conflict that is
  refused, not overwritten.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.adapters import AdapterRegistry  # noqa: E402
from core.engine import ThemeEngine  # noqa: E402
from core.errors import AdapterError  # noqa: E402
from core.filesystem import sha256_file  # noqa: E402

from adapters.gtk import direct as gtk_direct  # noqa: E402
from adapters.gtk.adapter import (  # noqa: E402
    MODE_KDE_SYNC,
    MODE_OBSERVE,
    GtkAdapter,
)

NO_WALLPAPER_TOML = '[theme]\nname = "T"\nid = "t"\nversion = 1\nmode = "dark"\n'

KCM = "/usr/bin/kcmshell6"


def _theme(make_theme, name: str | None = None, **kwargs):
    from core.theme_loader import load_theme

    return load_theme(make_theme(name=name, **kwargs))


def _gtk_env(config_home, *, versions=("gtk-3.0",), settings=""):
    config_home.mkdir(parents=True, exist_ok=True)
    for version in versions:
        d = config_home / version
        d.mkdir(parents=True, exist_ok=True)
        if settings:
            (d / "settings.ini").write_text(settings)
    return config_home


def _adapter(config_home, *, kcmshell6: str | None = None, **kwargs):
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


def _tree(config_home):
    return {p: sha256_file(p) if p.is_file() else "dir"
            for p in sorted(config_home.rglob("*"))}


class TestDefaultsTouchNothing:
    def test_observe_mode_writes_nothing(self, tmp_path, make_theme,
                                         context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        ctx = context_factory(theme=_theme(make_theme))
        before = _tree(cfg)
        adapter = _adapter(cfg)
        plan = adapter.plan(ctx.theme, ctx)
        result = adapter.apply(plan, ctx)

        assert plan.mode == MODE_OBSERVE
        assert result.applied is True and not result.errors
        assert _tree(cfg) == before
        # KDE-owned files are never fabricated by Omni
        assert not (cfg / "kdeglobals").exists()
        assert not (cfg / "gtk-3.0" / "colors.css").exists()
        assert not (cfg / "gtk-3.0" / "gtk.css").exists()

    def test_sync_mode_beats_direct_optin(self, tmp_path, make_theme,
                                          context_factory):
        """KDE owns color propagation; allow_direct must not fight it."""
        cfg = _gtk_env(
            tmp_path / "cfg",
            settings="[Settings]\ngtk-theme-name=Breeze\n",
        )
        ctx = context_factory(theme=_theme(make_theme))
        before = _tree(cfg)
        adapter = _adapter(cfg, kcmshell6=KCM, allow_direct=True)
        plan = adapter.plan(ctx.theme, ctx)
        result = adapter.apply(plan, ctx)

        assert plan.mode == MODE_KDE_SYNC
        assert not plan.direct_plans
        assert result.applied is True and not result.errors
        assert _tree(cfg) == before


class TestDirectOwnedTarget:
    def test_only_the_managed_block_file_is_touched(self, tmp_path,
                                                    make_theme,
                                                    context_factory):
        cfg = _gtk_env(tmp_path / "cfg", versions=("gtk-3.0", "gtk-4.0"))
        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True)
        plan = adapter.plan(ctx.theme, ctx)
        result = adapter.apply(plan, ctx)

        assert result.applied is True and not result.errors
        target = cfg / "gtk-3.0" / "gtk.css"
        text = target.read_text()
        assert gtk_direct.BEGIN_MARKER_PREFIX in text
        assert gtk_direct.END_MARKER in text
        assert "owner = omni-theme-cachy" in text
        # nothing else in the config home changed hands
        assert not (cfg / "kdeglobals").exists()
        assert not (cfg / "gtk-3.0" / "colors.css").exists()
        assert list((cfg / "gtk-4.0").iterdir()) == []

    def test_never_readonly_bits(self, tmp_path, make_theme,
                                 context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True)
        result = adapter.apply(adapter.plan(ctx.theme, ctx), ctx)
        assert result.applied
        target = cfg / "gtk-3.0" / "gtk.css"
        assert target.stat().st_mode & 0o200  # owner-writable

    def test_repeated_direct_application_replaces_block(self, tmp_path,
                                                        make_theme,
                                                        context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True)
        first = adapter.plan(ctx.theme, ctx)
        adapter.apply(first, ctx)
        target = cfg / "gtk-3.0" / "gtk.css"

        ctx2 = context_factory(theme=_theme(make_theme, "second"))
        second = adapter.plan(ctx2.theme, ctx2)
        adapter.apply(second, ctx2)

        assert target.read_text().count(gtk_direct.BEGIN_MARKER_PREFIX) == 1
        assert second.direct_plans[0].action == "replace-block"

    def test_external_modification_detected_after_write(self, tmp_path,
                                                        make_theme,
                                                        context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True)
        plan = adapter.plan(ctx.theme, ctx)
        adapter.apply(plan, ctx)
        target = cfg / "gtk-3.0" / "gtk.css"
        target.write_text(target.read_text().replace("#14161c", "#ffffff"))

        result = adapter.verify(plan, ctx)
        assert result.verified is False
        assert any("does not match planned content" in e
                   for e in result.errors)


class TestOwnershipConflict:
    def test_foreign_gtkcss_is_refused(self, tmp_path, make_theme,
                                       context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        target = cfg / "gtk-3.0" / "gtk.css"
        user_css = "/* user css */\nbutton { all: unset; }\n"
        target.write_text(user_css)

        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True)
        with pytest.raises(AdapterError, match="refusing"):
            adapter.plan(ctx.theme, ctx)
        assert target.read_text() == user_css

    def test_conflict_through_engine_fails_activation(self, fake_home,
                                                      make_theme):
        cfg = fake_home / ".config"
        _gtk_env(cfg)
        (cfg / "gtk-3.0" / "gtk.css").write_text("/* user css */\n")
        registry = AdapterRegistry()
        registry.register(_adapter(cfg, allow_direct=True))
        eng = ThemeEngine(
            themes_root=fake_home / "themes",
            templates_root=PROJECT_ROOT / "templates",
            state_root=fake_home / ".local" / "state" / "omni-theme",
            adapters=registry,
        )
        outcome = eng.apply(make_theme(name="conflict",
                                       theme_toml=NO_WALLPAPER_TOML))

        # Adapter-level errors degrade the activation loudly instead of
        # failing hard: the refusal is in the gtk result and the user's
        # file is byte-identical.
        assert outcome.status == "DEGRADED"
        gtk_result = next(r for r in outcome.adapter_results
                          if r.adapter_id == "gtk")
        assert any("refusing" in e for e in gtk_result.errors)
        assert (cfg / "gtk-3.0" / "gtk.css").read_text() == "/* user css */\n"


class TestRollbackOwnership:
    def test_rollback_restores_pre_omni_bytes(self, tmp_path, make_theme,
                                              context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        target = cfg / "gtk-3.0" / "gtk.css"
        original = "#user {\n  color: red;\n}\n"
        target.write_text(original)

        ctx = context_factory(theme=_theme(make_theme))
        adapter = _adapter(cfg, allow_direct=True, direct_force=True)
        plan = adapter.plan(ctx.theme, ctx)
        assert plan.direct_plans[0].previous_hash == sha256_file(target)
        adapter.apply(plan, ctx)

        result = adapter.rollback(None, ctx)
        assert result.rolled_back is True
        assert target.read_text() == original

    def test_sync_and_observe_modes_own_nothing(self, tmp_path, make_theme,
                                                context_factory):
        cfg = _gtk_env(tmp_path / "cfg")
        ctx = context_factory(theme=_theme(make_theme))
        result = _adapter(cfg).rollback(None, ctx)
        assert result.rolled_back is True
        assert any("owns no files" in w for w in result.warnings)
