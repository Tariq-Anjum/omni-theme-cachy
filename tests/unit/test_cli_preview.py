"""Tests for the CLI theme preview command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cli import main


def test_preview_with_valid_theme(tmp_path, make_theme):
    """`omni theme preview <name>` with a valid theme succeeds."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "preview", "test", "--root", str(tmp_path)])
    # Should succeed (dry_run is read-only)
    assert code == 0


def test_preview_with_json(tmp_path, make_theme, capsys):
    """`omni theme preview <name> --json` emits parseable JSON."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "preview", "test", "--root", str(tmp_path), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    # Should have required fields
    assert data["schema_version"] == 1
    assert data["command"] == "theme.preview"
    assert "ok" in data
    assert "theme" in data
    assert "adapters" in data
    assert "targets" in data
    assert "warnings" in data


def test_preview_with_json_output(capsys, tmp_path, make_theme):
    """`omni theme preview --json` outputs valid JSON."""
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "preview", "test", "--root", str(tmp_path), "--json"])
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "schema_version" in data


def test_preview_missing_theme(tmp_path):
    """`omni theme preview <name>` with missing theme returns error."""
    code = main(["theme", "preview", "nonexistent", "--root", str(tmp_path)])
    # Should be some error code
    assert code != 0


def test_preview_does_not_modify_state(tmp_path, make_theme):
    """Preview should be a dry-run that does not modify state."""
    import json
    theme = make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    # Set up state
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text('{"schema_version":1,"current_theme":null,"previous_theme":null,"activated_at":null,"current_generation":null,"previous_generation":null,"managed_targets":[],"adapters":{}}')
    # Run preview
    main(["theme", "preview", "test", "--root", str(tmp_path)])
    # State should be unchanged
    state = json.loads((state_dir / "state.json").read_text())
    assert state["current_theme"] is None