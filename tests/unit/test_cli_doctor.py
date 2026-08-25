"""Tests for the CLI doctor command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cli import main


def test_doctor_runs():
    """`omni doctor` should exit 0."""
    code = main(["doctor"])
    assert code == 0  # ExitCode.SUCCESS


def test_doctor_json_output(capsys):
    """`omni doctor --json` emits parseable JSON."""
    code = main(["doctor", "--json"])
    assert code == 0
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


def test_doctor_with_json_flag(capsys):
    """`omni doctor --json` outputs valid JSON."""
    code = main(["doctor", "--json"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    # Verify all required keys exist
    assert "os" in data
    assert "desktop" in data
    assert "python_version" in data
    assert "missing_binaries" in data
    assert "runtime_directory" in data