"""Tests for the CLI status command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cli import main


def test_status_no_state(tmp_path, capsys):
    """`omni status` with no state returns success (informational)."""
    code = main(["status", "--root", str(tmp_path), "--state-root", str(tmp_path / "st")])
    assert code == 0  # ExitCode.SUCCESS


def test_status_with_state(state_root, tmp_path, capsys):
    """`omni status` with a consistent state returns success and shows info."""
    code = main(
        ["status", "--root", str(tmp_path), "--state-root", str(state_root)]
    )
    assert code == 0  # Consistent state
    out = capsys.readouterr().out
    assert "test" in out


def test_status_with_json(state_root, tmp_path, capsys):
    """`omni status --json` emits parseable, consistent JSON."""
    code = main(
        ["status", "--root", str(tmp_path), "--state-root", str(state_root), "--json"]
    )
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["current_theme"] == "test"
    assert data["previous_theme"] == "old"
    assert data["current_generation"] == "gen-1"
    assert data["previous_generation"] == "gen-0"
    assert "managed_targets" in data
    assert "adapters" in data
    assert data["consistent"] is True


def test_status_json_output(state_root, tmp_path, capsys):
    """`omni status --json` outputs valid JSON with all required fields."""
    code = main(
        ["status", "--root", str(tmp_path), "--state-root", str(state_root), "--json"]
    )
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    for key in (
        "current_theme",
        "previous_theme",
        "current_generation",
        "previous_generation",
        "activated_at",
        "managed_targets",
        "adapters",
        "consistent",
    ):
        assert key in data


def test_status_inconsistent_state(tmp_path):
    """A state whose pointers diverge from the record is reported as CONFLICT."""
    from core.cli import ExitCode

    state_dir = tmp_path / "st"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        '{"schema_version":1,"current_theme":"test","previous_theme":null,'
        '"activated_at":null,"current_generation":"gen-9","previous_generation":null,'
        '"managed_targets":[],"adapters":{}}'
    )
    code = main(["status", "--root", str(tmp_path), "--state-root", str(state_dir)])
    assert code == ExitCode.CONFLICT