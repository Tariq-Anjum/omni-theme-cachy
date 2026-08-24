"""Unit tests for the targets.toml registry loader (session 03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.errors import TargetsError
from core.targets import load_targets


def make_registry(
    tmp_path,
    body: str,
    *,
    template_name: str = "kde/test.colors.tpl",
    template_body: str = "accent={{ accent }}",
):
    """Templates root with one real template + a registry file."""
    root = tmp_path / "templates"
    tpl = root / template_name
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_text(template_body)
    registry = root / "targets.toml"
    registry.write_text(body)
    return registry, root


VALID_ONE = """
[[template]]
adapter = "kde-colorscheme"

[template.source]
path = "kde/test.colors.tpl"

[template.target]
path = "~/.local/share/color-schemes/Test.colors"
"""


class TestHappyPath:
    def test_valid_entry_loads(self, tmp_path):
        registry, root = make_registry(tmp_path, VALID_ONE)
        entries = load_targets(registry, templates_root=root)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.name == "kde/test.colors.tpl"
        assert entry.source_path == root / "kde" / "test.colors.tpl"
        assert entry.target_path == Path("~/.local/share/color-schemes/Test.colors").expanduser()
        assert entry.adapter == "kde-colorscheme"

    def test_explicit_empty_registry_is_allowed(self, tmp_path):
        registry, root = make_registry(tmp_path, "template = []\n")
        assert load_targets(registry, templates_root=root) == []

    def test_adapter_optional(self, tmp_path):
        body = VALID_ONE.replace('adapter = "kde-colorscheme"\n', "")
        registry, root = make_registry(tmp_path, body)
        assert load_targets(registry, templates_root=root)[0].adapter is None


class TestStrictRejection:
    def test_missing_registry_file(self, tmp_path):
        with pytest.raises(TargetsError, match="missing targets registry"):
            load_targets(tmp_path / "nope.toml", templates_root=tmp_path)

    def test_invalid_toml(self, tmp_path):
        registry, root = make_registry(tmp_path, "[[template\n")
        with pytest.raises(TargetsError, match="invalid TOML"):
            load_targets(registry, templates_root=root)

    def test_missing_template_key(self, tmp_path):
        registry, root = make_registry(tmp_path, "other = 1\n")
        with pytest.raises(TargetsError, match="missing 'template' key"):
            load_targets(registry, templates_root=root)

    def test_template_key_wrong_type(self, tmp_path):
        registry, root = make_registry(tmp_path, 'template = "x"\n')
        with pytest.raises(TargetsError, match="array"):
            load_targets(registry, templates_root=root)

    def test_unknown_top_level_key(self, tmp_path):
        registry, root = make_registry(tmp_path, 'extra = "x"\n' + VALID_ONE)
        with pytest.raises(TargetsError, match="unknown top-level key"):
            load_targets(registry, templates_root=root)

    BAD_BODIES = {
        "unknown entry key": (
            "\n[[template]]\nunknown_key = true\n"
            '[template.source]\npath = "kde/test.colors.tpl"\n'
            '[template.target]\npath = "~/out"\n',
            r"unknown key\(s\): unknown_key",
        ),
        "blank adapter": (
            '\n[[template]]\nadapter = ""\n'
            '[template.source]\npath = "kde/test.colors.tpl"\n'
            '[template.target]\npath = "~/out"\n',
            "adapter must be a non-empty string",
        ),
        "relative destination": (
            "\n[[template]]\n"
            '[template.source]\npath = "kde/test.colors.tpl"\n'
            '[template.target]\npath = "relative/path"\n',
            "absolute or '~/'",
        ),
        "dotdot destination": (
            "\n[[template]]\n"
            '[template.source]\npath = "kde/test.colors.tpl"\n'
            '[template.target]\npath = "~/.x/../escape"\n',
            "'..'",
        ),
        "dotdot source": (
            "\n[[template]]\n"
            '[template.source]\npath = "../outside.tpl"\n'
            '[template.target]\npath = "~/out"\n',
            "'..'",
        ),
        "absolute source": (
            "\n[[template]]\n"
            '[template.source]\npath = "/abs/path.tpl"\n'
            '[template.target]\npath = "~/out"\n',
            "relative and posix-style",
        ),
        "source without tpl suffix": (
            "\n[[template]]\n"
            '[template.source]\npath = "kde/test.colors"\n'
            '[template.target]\npath = "~/out"\n',
            "'.tpl'",
        ),
        "ghost source file": (
            "\n[[template]]\n"
            '[template.source]\npath = "kde/ghost.tpl"\n'
            '[template.target]\npath = "~/out"\n',
            "not found",
        ),
        "missing source table": (
            '\n[[template]]\n[template.target]\npath = "~/out"\n',
            r"missing \[template\.source\]",
        ),
        "missing target table": (
            '\n[[template]]\n[template.source]\npath = "kde/test.colors.tpl"\n',
            r"missing \[template\.target\]",
        ),
    }

    @pytest.mark.parametrize(("label",), [(k,) for k in BAD_BODIES])
    def test_bad_entries_rejected(self, tmp_path, label):
        body, match = self.BAD_BODIES[label]
        registry, root = make_registry(tmp_path, body)
        with pytest.raises(TargetsError, match=match):
            load_targets(registry, templates_root=root)

    def test_duplicate_source_rejected(self, tmp_path):
        one = """
[[template]]
[template.source]
path = "kde/test.colors.tpl"
[template.target]
path = "~/a"

[[template]]
[template.source]
path = "kde/test.colors.tpl"
[template.target]
path = "~/b"
"""
        registry, root = make_registry(tmp_path, one)
        with pytest.raises(TargetsError, match="duplicate source"):
            load_targets(registry, templates_root=root)

    def test_duplicate_target_rejected(self, tmp_path):
        second = (tmp_path / "templates" / "kde" / "second.tpl")
        second.parent.mkdir(parents=True, exist_ok=True)
        second.write_text("x={{ accent }}")
        two = """
[[template]]
[template.source]
path = "kde/test.colors.tpl"
[template.target]
path = "~/same"

[[template]]
[template.source]
path = "kde/second.tpl"
[template.target]
path = "~/same"
"""
        registry, root = make_registry(tmp_path, two)
        with pytest.raises(TargetsError, match="duplicate target"):
            load_targets(registry, templates_root=root)
