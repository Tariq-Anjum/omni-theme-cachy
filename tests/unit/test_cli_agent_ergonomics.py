"""Agent-ergonomics contract tests: ``--yes``, ``--json``, ``commands``.

Pins the machine-readable CLI surface consumed by automation (and by
Session 17's OpenCode integration): every JSON document is versioned,
stdout carries JSON only, mutating commands are gated by ``--yes``, and
``omni commands`` reports per-command safety metadata derived from the
live parser so it cannot drift from the real surface.
"""

from __future__ import annotations

import builtins
import json

import pytest

from core.cli import ExitCode, _build_parser, _commands_metadata, _iter_leaf_parsers, main

FULL_INVOCATIONS = {
    "theme.list": ["theme", "list", "--json"],
    "theme.validate": ["theme", "validate", "test", "--json"],
    "theme.preview": ["theme", "preview", "test", "--json"],
    "theme.apply-dry": ["theme", "apply", "test", "--dry-run", "--json"],
    "status": ["status", "--json"],
    "doctor": ["doctor", "--json"],
    "version": ["version", "--json"],
    "commands": ["commands", "--json"],
}


def test_commands_json_is_valid(capsys):
    """`omni commands --json` emits a versioned, parseable inventory."""
    code = main(["commands", "--json"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == 1
    assert data["command"] == "commands"
    entries = data["commands"]
    assert isinstance(entries, list) and entries
    for entry in entries:
        assert set(entry) == {
            "name", "mutates", "supports_yes",
            "supports_json", "supports_dry_run",
        }
        assert isinstance(entry["mutates"], bool)
        assert isinstance(entry["supports_yes"], bool)
        assert isinstance(entry["supports_json"], bool)
        assert isinstance(entry["supports_dry_run"], bool)
    names = [entry["name"] for entry in entries]
    assert "commands" in names  # the inventory describes itself


def test_commands_metadata_is_stable():
    """Pin the exact inventory shape Session 17 will consume."""
    by_name = {entry["name"]: entry for entry in _commands_metadata()}
    assert set(by_name) == {
        "theme.list", "theme.validate", "theme.preview", "theme.apply",
        "theme.create", "theme.current", "theme.rollback",
        "status", "wallpaper.list", "wallpaper.current", "wallpaper.set",
        "doctor", "version", "commands",
    }
    assert by_name["theme.create"] == {
        "name": "theme.create",
        "mutates": True,
        "supports_yes": True,
        "supports_json": True,
        "supports_dry_run": False,
    }
    assert by_name["theme.apply"] == {
        "name": "theme.apply",
        "mutates": True,
        "supports_yes": True,
        "supports_json": True,
        "supports_dry_run": True,
    }
    assert by_name["theme.rollback"]["mutates"] is True
    assert by_name["theme.rollback"]["supports_yes"] is True
    assert by_name["theme.rollback"]["supports_dry_run"] is False
    assert by_name["wallpaper.set"]["mutates"] is True
    assert by_name["wallpaper.set"]["supports_yes"] is True
    assert by_name["wallpaper.set"]["supports_dry_run"] is False
    assert by_name["theme.preview"]["mutates"] is False
    assert by_name["theme.preview"]["supports_json"] is True


def test_all_mutating_commands_expose_yes():
    """Every mutating command accepts --yes; no read-only command does."""
    for entry in _commands_metadata():
        if entry["mutates"]:
            assert entry["supports_yes"], entry["name"]
        else:
            assert not entry["supports_yes"], entry["name"]


def test_parser_confirms_yes_on_mutating_commands():
    """Cross-check the raw parser, independent of the metadata derivation."""
    leaves = dict(_iter_leaf_parsers(_build_parser()))
    for name in ("theme.apply", "theme.rollback", "wallpaper.set"):
        options = {
            opt for action in leaves[name]._actions
            for opt in action.option_strings
        }
        assert "--yes" in options, name


def test_commands_human_output_smoke(capsys):
    """`omni commands` (human mode) lists commands and safety markers."""
    code = main(["commands"])
    assert code == ExitCode.SUCCESS
    out = capsys.readouterr().out
    assert "theme.apply" in out
    assert "mutates" in out
    assert "theme.list" in out


def test_apply_yes_does_not_prompt(tmp_path, capsys, make_theme, monkeypatch):
    """`apply --yes` must never prompt: no input(), no prompt text, no hang."""

    def _no_input(*args, **kwargs):  # pragma: no cover - failure signal
        raise AssertionError("prompt leaked: input() was called")

    monkeypatch.setattr(builtins, "input", _no_input)
    make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "apply", "test", "--root", str(tmp_path), "--yes"])
    assert code != ExitCode.USAGE
    captured = capsys.readouterr()
    assert "[y/N]" not in captured.out + captured.err


def test_rollback_yes_deterministic_exit_code(tmp_path, capsys):
    """`rollback --yes` without prior state fails deterministically."""
    code = main(["theme", "rollback", "--root", str(tmp_path), "--yes"])
    assert code == ExitCode.ROLLBACK_FAILURE


def test_apply_dry_run_json_parseable(tmp_path, capsys, make_theme):
    """`apply --dry-run --json` emits a parseable, versioned plan."""
    make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    code = main(["theme", "apply", "test", "--root", str(tmp_path),
                 "--dry-run", "--json"])
    assert code == ExitCode.SUCCESS
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == 1
    assert data["dry_run"] is True
    assert "ok" in data


def test_json_only_on_stdout(tmp_path, capsys, make_theme):
    """--json keeps stdout to one JSON document; no diagnostics on success."""
    make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    for argv in FULL_INVOCATIONS.values():
        argv = list(argv)
        if "--json" in argv and argv[0] == "theme":
            argv += ["--root", str(tmp_path)]
        code = main(argv)
        assert code == ExitCode.SUCCESS, argv
        captured = capsys.readouterr()
        assert not captured.err, argv
        data = json.loads(captured.out)  # stdout must be exactly one document
        assert isinstance(data, dict), argv


def test_schema_version_is_omnipresent(tmp_path, capsys, make_theme):
    """Every JSON surface (success or failure) carries schema_version == 1."""
    make_theme("test", theme_toml='[theme]\nname="Test"\nid="test"\nversion=1\nmode="dark"\n')
    invocations = list(FULL_INVOCATIONS.values()) + [
        ["theme", "validate", "nonexistent", "--json", "--root", str(tmp_path)],
        ["theme", "preview", "nonexistent", "--json", "--root", str(tmp_path)],
        ["theme", "current", "--json", "--root", str(tmp_path)],
    ]
    for argv in invocations:
        main(argv)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["schema_version"] == 1, argv
        assert data["command"], argv


def test_wallpaper_json_schema_version(capsys):
    """Wallpaper JSON surfaces are versioned when they emit output.

    On machines without a Plasma session these commands may fail before
    printing; in that case there is no document to check.
    """
    for argv in (["wallpaper", "list", "--json"], ["wallpaper", "current", "--json"]):
        main(argv)
        captured = capsys.readouterr()
        if captured.out.strip():
            data = json.loads(captured.out)
            assert data["schema_version"] == 1, argv
            assert data["command"], argv
