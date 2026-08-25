"""Tests for CLI exit codes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.cli import ExitCode, main


def test_exit_code_values():
    """Verify ExitCode enum values match the spec."""
    assert ExitCode.SUCCESS == 0
    assert ExitCode.USAGE == 2
    assert ExitCode.VALIDATION_ERROR == 10
    assert ExitCode.CONFLICT == 11
    assert ExitCode.UNSUPPORTED == 12
    assert ExitCode.ACTIVATION_FAILURE == 13
    assert ExitCode.ROLLBACK_FAILURE == 14
    assert ExitCode.INTERNAL_ERROR == 20


def test_validate_returns_correct_exit_codes(tmp_path, capsys, make_theme):
    """`omni theme validate` returns the documented exit codes."""
    # A validation-clean theme (palette + surfaces + real wallpaper).
    theme = make_theme(
        "good",
        theme_toml='[theme]\nname="Good"\nid="good"\nversion=1\nmode="dark"\n'
                   '[wallpaper]\ndefault="wallpapers/good.png"\n',
    )
    (theme / "wallpapers").mkdir(parents=True, exist_ok=True)
    (theme / "wallpapers" / "good.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    code = main(["theme", "validate", "good", "--root", str(tmp_path)])
    assert code == ExitCode.SUCCESS

    # Unresolvable reference is an engine error (consistent with preview).
    code = main(["theme", "validate", "missing", "--root", str(tmp_path)])
    assert code == ExitCode.INTERNAL_ERROR

    # Warnings are fatal only under --strict; this theme is clean.
    code = main(["theme", "validate", "good", "--root", str(tmp_path), "--strict"])
    assert code == ExitCode.SUCCESS


def test_preview_returns_correct_exit_codes(tmp_path, capsys, make_theme):
    """`omni theme preview` returns correct exit codes."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "preview", "test", "--root", str(tmp_path)])
    # Should succeed (dry_run always works if theme loads)
    assert code == ExitCode.SUCCESS

    # Missing theme
    code = main(["theme", "preview", "missing", "--root", str(tmp_path)])
    assert code == ExitCode.INTERNAL_ERROR


def test_apply_returns_correct_exit_codes(tmp_path, capsys, make_theme):
    """`omni theme apply` returns correct exit codes."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    # Without --yes in non-TTY should fail
    code = main(["theme", "apply", "test", "--root", str(tmp_path)])
    assert code == ExitCode.USAGE

    # With --yes should succeed (if theme is valid)
    code = main(["theme", "apply", "test", "--root", str(tmp_path), "--yes"])
    # Might fail due to missing adapters, but should not be USAGE
    assert code != ExitCode.USAGE


def test_rollback_returns_correct_exit_codes(tmp_path, capsys):
    """`omni theme rollback` returns correct exit codes."""
    # Without --yes in non-TTY should fail
    code = main(["theme", "rollback", "--root", str(tmp_path)])
    assert code == ExitCode.USAGE

    # With --yes should fail due to no previous state, but not USAGE
    code = main(["theme", "rollback", "--root", str(tmp_path), "--yes"])
    assert code == ExitCode.ROLLBACK_FAILURE  # No previous generation


def test_status_returns_correct_exit_codes(tmp_path, capsys):
    """`omni status` returns correct exit codes."""
    # No state
    code = main(["status", "--root", str(tmp_path)])
    assert code == ExitCode.SUCCESS  # Informational, not an error

    # With state
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text('{"schema_version":1,"current_theme":null,"previous_theme":null,"activated_at":null,"current_generation":null,"previous_generation":null,"managed_targets":[],"adapters":{}}')
    code = main(["status", "--root", str(tmp_path), "--state-root", str(state_dir)])
    assert code == ExitCode.SUCCESS  # Consistent state


def test_doctor_returns_success(capsys):
    """`omni doctor` returns SUCCESS."""
    code = main(["doctor"])
    assert code == ExitCode.SUCCESS


def test_version_returns_success(capsys):
    """`omni version` returns SUCCESS."""
    code = main(["version"])
    assert code == ExitCode.SUCCESS


def test_wallpaper_commands_return_correct_codes(capsys):
    """Wallpaper commands return appropriate codes."""
    # These will fail due to missing KDE, but should not be USAGE
    code = main(["wallpaper", "list"])
    assert code != ExitCode.USAGE

    code = main(["wallpaper", "current"])
    assert code != ExitCode.USAGE

    code = main(["wallpaper", "set", "test.jpg"])
    assert code != ExitCode.USAGE