"""Adapter write-path coverage tests (session 12).

Session 08 proved the core pipeline routes every write through the
central validator. This file closes the remaining routing gaps at the
adapter layer: the snapshot/restore copy paths, the wallpaper cache
repair copy, and a representative adapter journal + external target all
must be observed by ``filesystem.validate_write_target``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters import support as adapter_support
from adapters.kde.wallpaper import ensure_cached
from core.activation import ActivationContext
from core.errors import PathPolicyError
from core.state import RuntimeState
from tests.security.test_write_coverage import validator_recorder  # noqa: F401


PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _context(state_root: Path) -> ActivationContext:
    return ActivationContext(
        state_root=state_root,
        generation_dir=state_root / "generation",
        manifest=None,
        theme=None,
        dry_run=False,
        previous_state=RuntimeState(),
    )


# ---------------------------------------------------------------------------
# Backup snapshot / restore (adapters.support)
# ---------------------------------------------------------------------------


def test_snapshot_and_restore_route_through_validator(
    tmp_path, validator_recorder
):
    target = tmp_path / "home" / ".config" / "gtk-3.0" / "gtk.css"
    target.parent.mkdir(parents=True)
    original = b"/* user css */\n"
    target.write_bytes(original)
    backup_dir = tmp_path / "state" / "adapters" / "gtk-backups"

    record = adapter_support.snapshot_file(target, backup_dir)
    assert record["existed_before"] is True
    backup_path = Path(record["backup_path"])
    assert str(backup_path) in {str(p) for p in validator_recorder}
    assert backup_path.read_bytes() == original

    validator_recorder.clear()
    target.write_bytes(b"/* omni css */\n")
    rolled, warnings = adapter_support.restore_snapshot(target, record)

    assert rolled, warnings
    assert target.read_bytes() == original
    assert str(target) in {str(p) for p in validator_recorder}


def test_restore_refuses_target_outside_approved_roots(
    allow, tmp_path
):
    """A tampered journal entry cannot aim the restore outside the roots."""
    target = tmp_path / "outside.conf"  # outside the approved root
    target.write_bytes(b"whatever\n")
    backup_dir = allow / "backups"
    backup_dir.mkdir()
    record = {
        "existed_before": True,
        "previous_hash": "0" * 64,
        "backup_path": str(backup_dir / "x.bak"),
    }
    (backup_dir / "x.bak").write_bytes(b"original\n")

    rolled, warnings = adapter_support.restore_snapshot(target, record)

    assert not rolled
    assert any("outside" in w for w in warnings)
    assert target.read_bytes() == b"whatever\n"


# ---------------------------------------------------------------------------
# Wallpaper cache repair copy (adapters.kde.wallpaper)
# ---------------------------------------------------------------------------


def test_wallpaper_cache_copy_routes_through_validator(
    tmp_path, validator_recorder
):
    source = tmp_path / "theme.png"
    source.write_bytes(PNG_MAGIC)
    cache = tmp_path / "state" / "adapters" / "wallpaper-cache" / "omni-abc123.png"

    ensure_cached(source, cache)

    assert cache.read_bytes() == PNG_MAGIC
    assert str(cache) in {str(p) for p in validator_recorder}


def test_wallpaper_cache_repair_is_atomic_and_validated(
    tmp_path, validator_recorder
):
    source = tmp_path / "theme.png"
    source.write_bytes(PNG_MAGIC)
    cache = tmp_path / "state" / "adapters" / "wallpaper-cache" / "omni-abc123.png"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"corrupted\n")

    ensure_cached(source, cache)

    assert cache.read_bytes() == PNG_MAGIC
    assert str(cache) in {str(p) for p in validator_recorder}
    # the repair went through the atomic install path: no debris siblings
    assert [p.name for p in cache.parent.iterdir()] == [cache.name]


# ---------------------------------------------------------------------------
# Adapter journal + external target (vscode as the representative site)
# ---------------------------------------------------------------------------


def test_vscode_settings_and_journal_route_through_validator(
    tmp_path, validator_recorder
):
    from adapters.vscode.adapter import Journal, VscodeAdapter, VscodePlan

    settings = tmp_path / "home" / ".config" / "Code" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    state_root = tmp_path / "state"

    plan = VscodePlan(
        settings_path=settings,
        customizations={"editorCursor.foreground": "#4f9eea"},
        generation="gen-x",
        theme_id="test",
    )
    result = VscodeAdapter().apply(plan, _context(state_root))

    assert result.applied, result.errors
    validated = {str(p) for p in validator_recorder}
    assert str(settings) in validated
    journal_path = state_root / "adapters" / "vscode.json"
    assert str(journal_path) in validated
    assert '"editorCursor.foreground": "#4f9eea"' in settings.read_text()


def test_vscode_journal_write_is_rejected_outside_approved_roots(
    allow, tmp_path
):
    """Journal persistence is policy-bound like every other write."""
    from adapters.vscode.adapter import Journal

    journal = Journal(path=tmp_path / "outside" / "vscode.json")
    with pytest.raises(PathPolicyError):
        journal.save()


def test_konsole_journal_write_is_policy_bound(allow, tmp_path):
    from adapters.konsole.adapter import Journal

    journal = Journal(path=tmp_path / "outside" / "konsole.json")
    from core.errors import PathPolicyError

    with pytest.raises(PathPolicyError):
        journal.save()
