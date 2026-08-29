"""Session 17: OpenCode integration contract tests.

Validate the project commands in .opencode/commands/ and the permission
config in opencode.json without depending on an installed opencode client.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMANDS_DIR = REPO_ROOT / ".opencode" / "commands"
CONFIG_PATH = REPO_ROOT / "opencode.json"

EXPECTED_COMMANDS = (
    "omni-check",
    "omni-preview",
    "omni-apply",
    "omni-security",
    "omni-release-check",
)

MUTATING_OMNI_COMMANDS = (
    "omni theme apply",
    "omni theme rollback",
    "omni wallpaper set",
)

DANGEROUS_PATTERNS = (
    # automatic push / tag / install instructions (prose "do not push" is fine)
    r"^\s*git\s+push\b",
    r"^\s*git\s+tag\b",
    r"^\s*pip\s+install\b",
    r"^\s*pip3\s+install\b",
    r"^\s*npm\s+install\b",
    r"^\s*sudo\s+",
    r"subprocess\.\w+\([^)]*shell=True",
)


def _command_files():
    return sorted(COMMANDS_DIR.glob("*.md"))


def _parse_frontmatter(text):
    """Parse a simple `key: value` markdown frontmatter block."""
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            return None
        meta[key.strip()] = value.strip()
    return meta


def test_command_files_exist():
    for name in EXPECTED_COMMANDS:
        assert (COMMANDS_DIR / f"{name}.md").is_file(), name


def test_command_names_unique():
    files = _command_files()
    names = [path.stem for path in files]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("path", _command_files(), ids=lambda p: p.stem)
def test_frontmatter_parseable(path):
    meta = _parse_frontmatter(path.read_text(encoding="utf-8"))
    assert meta is not None, f"{path.name}: frontmatter missing or unparseable"
    assert meta.get("description"), f"{path.name}: description missing"
    assert meta.get("agent"), f"{path.name}: agent missing"


@pytest.mark.parametrize("path", _command_files(), ids=lambda p: p.stem)
def test_commands_use_omni_cli(path):
    body = path.read_text(encoding="utf-8")
    if path.stem in ("omni-preview", "omni-apply", "omni-release-check"):
        assert "omni " in body, f"{path.name}: must wrap the omni CLI"


@pytest.mark.parametrize("path", _command_files(), ids=lambda p: p.stem)
def test_no_dangerous_automatic_instructions(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        for pattern in DANGEROUS_PATTERNS:
            assert not re.search(pattern, line), (
                f"{path.name}: dangerous instruction {pattern!r}: {line!r}"
            )


@pytest.mark.parametrize("path", _command_files(), ids=lambda p: p.stem)
def test_mutating_flow_gated_by_dry_run(path):
    body = path.read_text(encoding="utf-8")
    if path.stem == "omni-apply":
        assert "--dry-run" in body
        assert "--yes" in body


def test_referenced_scripts_exist():
    body = "\n".join(
        path.read_text(encoding="utf-8") for path in _command_files()
    )
    for script in ("scripts/audit_omarchy_divergence.py", "scripts/audit_write_paths.py"):
        assert (REPO_ROOT / script).is_file(), script
        assert script in body


def test_opencode_config_valid_and_conservative():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert config.get("$schema") == "https://opencode.ai/config.json"
    permission = config["permission"]
    assert permission["read"] == "allow"
    assert permission["glob"] == "allow"
    assert permission["grep"] == "allow"
    assert permission["webfetch"] == "allow"
    assert permission["edit"] == "ask"
    bash = permission["bash"]
    assert bash["*"] == "ask"
    assert bash["git push*"] == "ask"
    assert bash["git tag*"] == "ask"
    for deny in ("pip install*", "npm install*", "sudo *"):
        assert bash[deny] == "deny"


def test_readonly_omni_commands_allowed_without_prompting():
    bash = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["permission"]["bash"]
    for pattern in (
        "omni theme list*",
        "omni theme validate*",
        "omni theme preview*",
        "omni status*",
        "omni doctor*",
        "omni commands*",
    ):
        assert bash.get(pattern) == "allow", pattern


def test_mutating_omni_commands_not_preallowed():
    bash = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["permission"]["bash"]
    for command in MUTATING_OMNI_COMMANDS:
        assert command not in bash
