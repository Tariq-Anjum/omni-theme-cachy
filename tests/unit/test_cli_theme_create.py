"""Tests for `omni theme create` (wallpaper → theme CLI command)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.cli import ExitCode, main

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_wallpaper_extractor import write_png  # noqa: E402


@pytest.fixture
def wallpaper(tmp_path: Path) -> Path:
    """A small two-tone PNG wallpaper."""
    pixels = [(20, 24, 38)] * 400 + [(226, 214, 182)] * 400
    return write_png(tmp_path / "sunset.png", pixels, 40, 20)


def test_create_writes_loadable_theme(tmp_path, capsys, wallpaper):
    root = tmp_path / "themes"
    code = main([
        "theme", "create", "--from-wallpaper", str(wallpaper),
        "--name", "Sunset Test", "--root", str(root), "--yes", "--json",
    ])
    assert code == ExitCode.SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] and payload["theme"]["id"] == "sunset-test"
    theme_dir = Path(payload["theme"]["source"])
    assert (theme_dir / "theme.toml").is_file()
    assert (theme_dir / "wallpapers" / "sunset.png").is_file()

    # The generated theme appears in `omni theme list` for that root.
    main(["theme", "list", "--root", str(root), "--json"])
    listing = json.loads(capsys.readouterr().out)
    assert any(t["id"] == "sunset-test" for t in listing["themes"])


def test_create_requires_confirmation_without_yes(tmp_path, capsys, wallpaper, monkeypatch):
    monkeypatch.setattr("sys.stdin", None)  # non-interactive
    code = main([
        "theme", "create", "--from-wallpaper", str(wallpaper),
        "--name", "NoConfirm", "--root", str(tmp_path / "themes"),
    ])
    assert code == ExitCode.USAGE
    assert not (tmp_path / "themes" / "noconfirm").exists()


def test_create_rejects_missing_wallpaper(tmp_path, capsys):
    code = main([
        "theme", "create", "--from-wallpaper", str(tmp_path / "ghost.png"),
        "--name", "Ghost", "--root", str(tmp_path / "themes"), "--yes", "--json",
    ])
    assert code == ExitCode.INTERNAL_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert not payload["ok"]
    assert "not found" in payload["errors"][0]


def test_create_refuses_existing_id_without_force(tmp_path, capsys, wallpaper):
    root = tmp_path / "themes"
    argv = [
        "theme", "create", "--from-wallpaper", str(wallpaper),
        "--name", "Dup", "--root", str(root), "--yes", "--json",
    ]
    assert main(argv) == ExitCode.SUCCESS
    assert main(argv) == ExitCode.INTERNAL_ERROR
    assert main(argv + ["--force"]) == ExitCode.SUCCESS


def test_commands_metadata_marks_create_mutating(capsys):
    main(["commands", "--json"])
    entries = json.loads(capsys.readouterr().out)["commands"]
    create = next(e for e in entries if e["name"] == "theme.create")
    assert create["mutates"] and create["supports_yes"] and create["supports_json"]
