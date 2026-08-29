"""Tests for CLI JSON output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cli import ExitCode, main


def test_theme_list_json_output(tmp_path, capsys, make_theme):
    """`omni theme list --json` emits a versioned, parseable document."""
    make_theme("foo", theme_toml='[theme]\nname="Foo"\nid="foo"\nversion=1\nmode="dark"\n')
    make_theme("bar", theme_toml='[theme]\nname="Bar"\nid="bar"\nversion=1\nmode="dark"\n')
    code = main(["theme", "list", "--root", str(tmp_path), "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == 1
    assert data["command"] == "theme.list"
    assert {t["id"] for t in data["themes"]} == {"foo", "bar"}


def test_doctor_json_output(capsys):
    """`omni doctor --json` emits parseable JSON."""
    code = main(["doctor", "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    # Should have all expected keys
    expected_keys = {
        "os", "desktop", "plasma_version", "session_type", "python_version",
        "missing_binaries", "xdg_directories", "runtime_directory",
        "current_theme", "previous_theme", "symlink_integrity",
        "managed_target_conflicts", "adapter_capabilities",
        "kde_color_scheme", "wallpaper_capability", "gtk_sync"
    }
    assert expected_keys.issubset(set(data.keys()))


def test_version_json_output(capsys):
    """`omni version` does not accept --json (no output change)."""
    # Version doesn't accept --json, so just test it runs
    code = main(["version"])
    assert code == ExitCode.SUCCESS


def test_status_json_output(tmp_path, capsys):
    """`omni status --json` emits parseable JSON."""
    # Create minimal state
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text('{"schema_version":1,"current_theme":null,"previous_theme":null,"activated_at":null,"current_generation":null,"previous_generation":null,"managed_targets":[],"adapters":{}}')
    code = main(["status", "--root", str(tmp_path), "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == 1
    assert "current_theme" in data


def test_preview_json_output(tmp_path, capsys, make_theme):
    """`omni theme preview --json` emits parseable JSON."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "preview", "test", "--root", str(tmp_path), "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    # Should have schema_version, command, ok, etc.
    assert data["schema_version"] == 1
    assert data["command"] == "theme.preview"
    assert "ok" in data
    assert "theme" in data


def test_validate_json_output_invalid(tmp_path, capsys):
    """`omni theme validate --json` on invalid theme returns ok=false."""
    code = main(["theme", "validate", "nonexistent", "--root", str(tmp_path), "--json"])
    assert code == ExitCode.INTERNAL_ERROR  # find_theme raises ThemeError
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["ok"] is False
    assert "issues" in data