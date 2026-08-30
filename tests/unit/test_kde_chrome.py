"""Tests for the plasma-chrome adapter (surgical KDE config edits)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.kde.chrome import (
    APPLETSRC,
    KDEGLOBALS,
    KWINRC,
    Journal,
    PlasmaChromeAdapter,
    journal_path,
)
from core import kde_config
from core.theme_model import Surfaces, Theme, ThemeMeta

PLASMA_ENV = {"XDG_CURRENT_DESKTOP": "KDE", "KDE_SESSION_VERSION": "6"}
APPLETSRC_TEXT = """[Containments][1]
plugin=org.kde.desktop

[Containments][277]
plugin=org.kde.panel
walls=false

[PlasmaViews][Panel 277][Defaults]
opacity=0
"""

KDEGLOBALS_TEXT = """[General]
ColorScheme=BreezeDark

[Colors:Tooltip]
BackgroundNormal=20, 48, 74
ForegroundNormal=252, 252, 252
"""


def make_adapter(tmp_path: Path, appletsrc: str | None = APPLETSRC_TEXT,
                 kdeglobals: str | None = KDEGLOBALS_TEXT) -> PlasmaChromeAdapter:
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    if appletsrc is not None:
        (config / APPLETSRC).write_text(appletsrc, encoding="utf-8")
    if kdeglobals is not None:
        (config / KDEGLOBALS).write_text(kdeglobals, encoding="utf-8")
    return PlasmaChromeAdapter(env=PLASMA_ENV, config_home=config)


def make_theme(surfaces: dict) -> Theme:
    return Theme(
        meta=ThemeMeta(name="T", id="t", version=1, mode="dark"),
        surfaces=Surfaces(surfaces),
    )


class Ctx:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root


# -- capability --------------------------------------------------------------


def test_capability_unsupported_without_plasma(tmp_path):
    adapter = PlasmaChromeAdapter(
        env={"XDG_CURRENT_DESKTOP": "GNOME"},
        which=lambda name: None,  # no Plasma binaries on PATH either
        config_home=tmp_path,
    )
    cap = adapter.capability(Ctx(tmp_path))
    assert not cap.supported


def test_capability_supported_with_plasma(tmp_path):
    assert make_adapter(tmp_path).capability(Ctx(tmp_path / "config")).supported


# -- planning ----------------------------------------------------------------


def test_panel_patch_targets_panel_containment_only(tmp_path):
    plan = make_adapter(tmp_path).plan(make_theme({"panel": {"opacity": "translucent"}}), None)
    assert [(p.section, p.key, p.value) for p in plan.patches] == [
        ("PlasmaViews][Panel 277][Defaults", "opacity", "1")
    ]


def test_opacity_codes_and_validation(tmp_path):
    adapter = make_adapter(tmp_path)
    for text, code in (("opaque", "0"), ("adaptive", "2"), (2, "2")):
        plan = adapter.plan(make_theme({"panel": {"opacity": text}}), None)
        assert plan.patches[0].value == code
    with pytest.raises(Exception, match="opacity"):
        adapter.build_patches(make_theme({"panel": {"opacity": "sparkly"}}))


def test_kwin_and_tooltip_patches(tmp_path):
    plan = make_adapter(tmp_path).plan(
        make_theme({
            "kwin": {"theme": "Sleeq", "library": "org.kde.kwin.aurorae"},
            "tooltips": {"background": "#1e222b", "foreground": "#d6dae2"},
            "unknown-group": {"ignored": True},
        }),
        None,
    )
    got = {(p.file, p.section, p.key): p.value for p in plan.patches}
    assert got[(KWINRC, "org.kde.kdecoration2", "theme")] == "Sleeq"
    assert got[(KWINRC, "org.kde.kdecoration2", "library")] == "org.kde.kwin.aurorae"
    assert got[(KDEGLOBALS, "Colors:Tooltip", "BackgroundNormal")] == "30,34,43"
    assert got[(KDEGLOBALS, "Colors:Tooltip", "ForegroundInactive")] == "214,218,226"
    assert all("unknown" not in p.section for p in plan.patches)


def test_theme_without_chrome_surfaces_plans_nothing(tmp_path):
    plan = make_adapter(tmp_path).plan(make_theme({"popups": {"border": "#ffffff"}}), None)
    assert plan.patches == ()
    assert plan.warnings


# -- apply / verify / rollback ------------------------------------------------


def _full_surfaces() -> dict:
    return {
        "panel": {"opacity": "translucent"},
        "kwin": {"theme": "Sleeq"},
        "tooltips": {"background": "#1e222b", "foreground": "#d6dae2"},
    }


def test_apply_then_verify_roundtrip(tmp_path):
    config = tmp_path / "config"
    adapter = make_adapter(tmp_path)
    plan = adapter.plan(make_theme(_full_surfaces()), None)
    ctx = Ctx(tmp_path)
    result = adapter.apply(plan, ctx)
    assert result.applied and not result.errors

    appletsrc = (config / APPLETSRC).read_text(encoding="utf-8")
    # The desktop containment is untouched; the panel group gained opacity=1.
    assert "[Containments][1]" in appletsrc and "walls=false" in appletsrc
    entries = kde_config.parse_ini(appletsrc)
    assert entries[("PlasmaViews][Panel 277][Defaults", "opacity")] == "1"

    kwin = kde_config.parse_ini((config / KWINRC).read_text(encoding="utf-8"))
    assert kwin[("org.kde.kdecoration2", "theme")] == "Sleeq"

    kg = kde_config.parse_ini((config / KDEGLOBALS).read_text(encoding="utf-8"))
    assert kg[("Colors:Tooltip", "BackgroundNormal")] == "30,34,43"
    assert kg[("General", "ColorScheme")] == "BreezeDark"  # other keys survive

    verified = adapter.verify(plan, ctx)
    assert verified.verified and not verified.errors


def test_apply_is_idempotent(tmp_path):
    adapter = make_adapter(tmp_path)
    ctx = Ctx(tmp_path)
    plan = adapter.plan(make_theme(_full_surfaces()), None)
    first = adapter.apply(plan, ctx)
    second = adapter.apply(plan, ctx)
    assert first.applied and second.applied
    appletsrc = (tmp_path / "config" / APPLETSRC).read_text(encoding="utf-8")
    assert appletsrc.count("opacity=1") == 1  # no duplicate keys


def test_rollback_restores_previous_bytes(tmp_path):
    config = tmp_path / "config"
    adapter = make_adapter(tmp_path)
    ctx = Ctx(tmp_path)
    plan = adapter.plan(make_theme(_full_surfaces()), None)
    adapter.apply(plan, ctx)

    rolled = adapter.rollback(None, ctx)
    assert rolled.rolled_back and not rolled.errors
    assert (config / APPLETSRC).read_text(encoding="utf-8") == APPLETSRC_TEXT
    assert (config / KDEGLOBALS).read_text(encoding="utf-8") == KDEGLOBALS_TEXT
    assert not (config / KWINRC).exists()  # created by us, removed again


def test_second_apply_snapshot_keeps_first(tmp_path):
    """Re-applying must never overwrite the journal's true pre-Omni bytes."""
    adapter = make_adapter(tmp_path)
    ctx = Ctx(tmp_path)
    plan = adapter.plan(make_theme(_full_surfaces()), None)
    adapter.apply(plan, ctx)
    journal = Journal.load(journal_path(ctx.state_root))
    first_snapshot = json.dumps(journal.snapshots[APPLETSRC], sort_keys=True)
    # Diverge the file, then re-apply: the snapshot must stay the original.
    adapter.apply(plan, ctx)
    journal2 = Journal.load(journal_path(ctx.state_root))
    assert json.dumps(journal2.snapshots[APPLETSRC], sort_keys=True) == first_snapshot


def test_bad_tooltip_color_reports_error(tmp_path):
    adapter = make_adapter(tmp_path)
    with pytest.raises(Exception, match="tooltips"):
        adapter.build_patches(make_theme({"tooltips": {"background": "not-a-color"}}))
