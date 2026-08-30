"""Guard tests: the engine never *owns* ``kwinrc`` (session 13).

Window behaviour, tiling, KWin scripts and global workflow preferences
are outside the theme engine's product scope (control-plane session 06/09
scope decisions). No code path may write ``kwinrc`` as a managed
whole-file artifact.

Control-plane decision (2026-08, user-directed): *window decoration
selection* is in scope through the :mod:`adapters.kde.chrome` adapter,
which performs key-level, journalled, byte-preserving edits via
:mod:`core.kde_config` (same ownership model as the Konsole adapter).
That adapter is the single sanctioned exception below; everything else —
whole-file kwinrc targets, behavioural KWin settings, scripts — stays
out of scope. These tests pin that boundary.

The guards scan repository sources only — they never read or write any
real user configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SOURCE_ROOTS = ("core", "adapters", "hooks", "scripts")

#: The one sanctioned seam (see module docstring): surgical, journalled
#: decoration-selection edits. Any other file mentioning kwinrc fails.
_KWINRC_ALLOWLIST = {"adapters/kde/chrome.py"}


def _python_sources() -> list[Path]:
    paths: list[Path] = []
    for root in _SOURCE_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            paths.append(path)
    return sorted(paths)


def test_source_tree_exists():
    """Sanity: the scan actually sees code (guards against silent no-ops)."""
    names = [p.name for p in _python_sources()]
    assert "kde_config.py" in names
    assert "adapter.py" in names


def test_no_source_references_kwinrc():
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if "kwinrc" in path.read_text(encoding="utf-8")
    ]
    unexpected = [h for h in hits if h not in _KWINRC_ALLOWLIST]
    assert unexpected == [], f"kwinrc referenced outside the sanctioned seam: {unexpected}"
    # The sanctioned seam must keep existing for the exception to make sense.
    assert set(hits) == _KWINRC_ALLOWLIST


def test_no_kwinrc_managed_target():
    registry = (REPO_ROOT / "templates" / "targets.toml").read_text(encoding="utf-8")
    assert "kwinrc" not in registry


@pytest.mark.parametrize(
    "forbidden", ["KWin reconfigure", "kwin_script", "set_kwin_setting"]
)
def test_no_kwin_mutation_seam_exists(forbidden):
    """No dedicated KWin mutation seam may exist while kwinrc is out of scope."""
    for path in _python_sources():
        assert forbidden not in path.read_text(encoding="utf-8"), (
            f"{path.relative_to(REPO_ROOT)} mentions {forbidden!r}"
        )
