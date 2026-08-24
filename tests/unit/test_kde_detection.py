"""Unit tests for KDE Plasma environment detection (fully hermetic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.kde.detection import (  # noqa: E402
    PLASMA_TOOLS,
    PlasmaEnvironment,
    detect_plasma,
)

KDE_TOOLS = {
    name: f"/usr/bin/{name}"
    for name in (
        "plasma-apply-colorscheme",
        "plasma-apply-wallpaperimage",
        "kreadconfig6",
        "qdbus6",
        "plasmashell",
    )
}


def _which_factory(tools):
    def which(name):
        return tools.get(name)

    return which


class TestDetectPlasma:
    def test_full_plasma6_environment(self):
        env = detect_plasma(
            env={
                "XDG_CURRENT_DESKTOP": "KDE",
                "XDG_SESSION_TYPE": "wayland",
            },
            which=_which_factory(KDE_TOOLS),
            version_runner=lambda argv: "plasmashell 6.7.4",
        )
        assert env.is_plasma_session
        assert env.plasmashell_version == "6.7.4"
        assert env.major_version == 6
        assert env.session_type == "wayland"
        assert env.has("plasma-apply-colorscheme")
        assert env.tool_path("kreadconfig6") == "/usr/bin/kreadconfig6"

    def test_non_kde_machine(self):
        env = detect_plasma(
            env={"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"},
            which=_which_factory({}),
            version_runner=lambda argv: None,
        )
        assert not env.is_plasma_session
        assert env.plasmashell_version is None
        assert env.major_version is None
        assert not any(env.has(tool) for tool in PLASMA_TOOLS)

    def test_bare_environment_no_variables(self):
        env = detect_plasma(
            env={},
            which=_which_factory(KDE_TOOLS),
            version_runner=lambda argv: "plasmashell 6.1.0",
        )
        # binaries exist but no session: still detected via plasmashell
        assert not env.is_plasma_session
        assert env.major_version == 6

    def test_colon_separated_desktop_list(self):
        env = detect_plasma(
            env={"XDG_CURRENT_DESKTOP": "KDE:GNOME"},
            which=_which_factory({}),
            version_runner=lambda argv: None,
        )
        assert env.is_plasma_session

    def test_unparsable_version_is_none_not_crash(self):
        env = detect_plasma(
            env={"XDG_CURRENT_DESKTOP": "KDE"},
            which=_which_factory({"plasmashell": "/usr/bin/plasmashell"}),
            version_runner=lambda argv: "plasmashell banana",
        )
        assert env.plasmashell_version is None

    def test_version_runner_failure_tolerated(self):
        def boom(argv):
            raise RuntimeError("no desktop")

        env = detect_plasma(
            env={"XDG_CURRENT_DESKTOP": "KDE"},
            which=_which_factory({"plasmashell": "/usr/bin/plasmashell"}),
            version_runner=boom,
        )
        assert env.plasmashell_version is None
        assert env.is_plasma_session

    def test_tools_reported_missing_when_absent(self):
        env = detect_plasma(
            env={"XDG_CURRENT_DESKTOP": "KDE"},
            which=_which_factory({"kreadconfig6": "/usr/bin/kreadconfig6"}),
            version_runner=lambda argv: None,
        )
        assert env.has("kreadconfig6")
        assert not env.has("qdbus6")


class TestPlasmaEnvironment:
    def test_defaults(self):
        env = PlasmaEnvironment(desktop=None, session_type=None,
                                plasmashell_version=None)
        assert not env.is_plasma_session
        assert env.major_version is None
        assert env.tool_path("anything") is None
