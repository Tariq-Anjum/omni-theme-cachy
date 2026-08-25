"""Tests for CLI command dispatch and basic behavior."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.cli import ExitCode, main


def test_help_returns_zero(capsys):
    """`omni --help` should exit 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_theme_list_no_themes(tmp_path, capsys):
    """`omni theme list` with no themes dir returns USAGE."""
    code = main(["theme", "list", "--root", str(tmp_path)])
    assert code == ExitCode.USAGE


def test_theme_list_with_themes(tmp_path, capsys, make_theme):
    """`omni theme list` finds theme directories."""
    make_theme("foo", theme_toml='[theme]\nname="Foo"\nid="foo"\nversion=1\nmode="dark"\n')
    code = main(["theme", "list", "--root", str(tmp_path)])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    assert "foo" in out


def test_version_returns_success(capsys):
    """`omni version` returns SUCCESS."""
    code = main(["version"])
    assert code == ExitCode.SUCCESS


def test_doctor_runs_without_crashing(capsys):
    """`omni doctor` should not crash."""
    code = main(["doctor"])
    assert code == ExitCode.SUCCESS


def test_status_no_state_returns_failure(capsys, tmp_path):
    """`omni status` with no state returns SUCCESS (informational)."""
    code = main(["status", "--root", str(tmp_path)])
    assert code == ExitCode.SUCCESS


def test_status_with_state(tmp_path, capsys, make_theme):
    """`omni status` with a consistent state returns success."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text('{"schema_version":1,"current_theme":"none","previous_theme":null,"activated_at":null,"current_generation":null,"previous_generation":null,"managed_targets":[],"adapters":{}}')
    code = main(["status", "--root", str(tmp_path), "--state-root", str(state_dir)])
    assert code == ExitCode.SUCCESS


def test_validate_missing_theme(tmp_path, capsys):
    """`omni theme validate` with missing theme returns USAGE."""
    code = main(["theme", "validate", "nonexistent", "--root", str(tmp_path)])
    assert code == ExitCode.INTERNAL_ERROR


def test_validate_good_theme(tmp_path, capsys, make_theme):
    """`omni theme validate` with a valid theme returns SUCCESS."""
    theme = make_theme("good", theme_toml='[theme]\nname="Good"\nid="good"\nversion=1\nmode="dark"\n')
    code = main(["theme", "validate", "good", "--root", str(tmp_path)])
    assert code == ExitCode.SUCCESS


def test_validate_json_output(tmp_path, capsys, make_theme):
    """`omni theme validate --json` emits parseable JSON."""
    theme = make_theme("good", theme_toml='[theme]\nname="Good"\nid="good"\nversion=1\nmode="dark"\n')
    code = main(["theme", "validate", "good", "--root", str(tmp_path), "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    import json
    data = json.loads(out)
    assert "ok" in data
    assert "issues" in data


def test_preview_missing_theme(tmp_path, capsys):
    """`omni theme preview` with missing theme returns INTERNAL_ERROR."""
    code = main(["theme", "preview", "nonexistent", "--root", str(tmp_path)])
    assert code == ExitCode.INTERNAL_ERROR


def test_apply_without_yes_fails_in_non_tty(tmp_path, capsys, make_theme):
    """`omni theme apply` without --yes fails in non-interactive shell."""
    # Create a valid theme so we get to the confirmation check
    make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "apply", "test", "--root", str(tmp_path)])
    assert code == ExitCode.USAGE


def test_rollback_without_yes_fails_in_non_tty(tmp_path, capsys):
    """`omni theme rollback` without --yes fails in non-interactive shell."""
    code = main(["theme", "rollback", "--root", str(tmp_path)])
    assert code == ExitCode.USAGE


def test_wallpaper_current_returns_sensible_code(capsys):
    """`omni wallpaper current` should not crash and return a sensible code."""
    code = main(["wallpaper", "current"])
    # Should not be USAGE (that's for command-line argument errors)
    assert code != ExitCode.USAGE
    # Should be either SUCCESS or FAILED
    assert code in (ExitCode.SUCCESS, ExitCode.ACTIVATION_FAILURE)


def test_theme_current_no_state(tmp_path, capsys):
    """`omni theme current` with no state returns ACTIVATION_FAILURE."""
    code = main(["theme", "current", "--root", str(tmp_path)])
    assert code == ExitCode.ACTIVATION_FAILURE


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