"""Guard tests: the engine never touches ``kwinrc`` (session 13).

Window behaviour, tiling, KWin scripts and global workflow preferences
are outside the theme engine's product scope (control-plane session 06/09
scope decisions). No code path may write ``kwinrc`` — not to create a
"seamless" experience, and not via any adapter. These tests pin that
boundary; a future session that legitimately needs KWin scope must
change these guards together with an explicit control-plane decision.

The guards scan repository sources only — they never read or write any
real user configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SOURCE_ROOTS = ("core", "adapters", "hooks", "scripts")


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
    assert hits == [], f"kwinrc referenced by code (write-scope guard): {hits}"


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
