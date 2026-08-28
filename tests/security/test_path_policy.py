"""Path-policy tests (session 08): traversal, escapes, sibling prefixes.

The approved roots under test are re-registered per test with
:func:`core.filesystem.set_approved_roots` and restored afterwards; the
autouse fixture normally points the policy at ``tmp_path``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import filesystem
from core.errors import PathPolicyError


@pytest.fixture
def allow(tmp_path):
    """Register ``tmp_path/allowed`` as the only approved root."""
    root = tmp_path / "allowed"
    root.mkdir()
    filesystem.set_approved_roots([root])
    yield root
    filesystem.set_approved_roots(None)


def test_rejects_relative_traversal(tmp_path):
    filesystem.set_approved_roots([tmp_path])
    try:
        escape = tmp_path / "sub" / ".." / ".." / "evil.conf"
        with pytest.raises(PathPolicyError, match="outside the approved write roots"):
            filesystem.validate_write_target(escape)
        assert not (tmp_path.parent / "evil.conf").exists()
    finally:
        filesystem.set_approved_roots(None)


def test_rejects_absolute_unrelated_path(allow):
    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(Path("/etc/passwd"))


def test_rejects_sibling_prefix_bypass(allow):
    # /allowed-evil must not slip past a check for /allowed.
    evil = allow.parent / "allowed-evil" / "x.conf"
    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(evil)


def test_rejects_symlink_escape_from_inside(allow, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = allow / "escape"
    link.symlink_to(outside)
    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(link / "written.conf")
    assert not (outside / "written.conf").exists()


def test_rejects_final_component_symlink_escape(allow, tmp_path):
    outside_file = tmp_path / "victim.conf"
    outside_file.write_text("original\n")
    link = allow / "f.conf"
    link.symlink_to(outside_file)
    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(link)
    assert outside_file.read_text() == "original\n"


def test_rejects_root_dotdot_escape(allow):
    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(allow / ".." / "allowed-evil")


def test_accepts_nested_legal_path(allow):
    resolved = filesystem.validate_write_target(allow / "a" / "b" / "c.conf")
    assert resolved == (allow / "a" / "b" / "c.conf").resolve(strict=False)


def test_accepts_nonexistent_legal_target(allow):
    missing = allow / "not" / "yet" / "here.conf"
    assert filesystem.validate_write_target(missing) == missing.resolve(strict=False)


def test_accepts_legal_existing_target(allow):
    target = allow / "real.conf"
    target.write_text("x\n")
    assert filesystem.validate_write_target(target) == target.resolve()


def test_default_roots_are_xdg_derived_and_narrow(fake_home):
    """The default allowlist is exactly the XDG base dirs; never $HOME or /."""
    filesystem.set_approved_roots(None)
    roots = filesystem.approved_roots()
    assert set(roots) == {
        filesystem.xdg_config_home().resolve(strict=False),
        filesystem.xdg_data_home().resolve(strict=False),
        filesystem.xdg_state_home().resolve(strict=False),
    }
    home = Path(os.environ["HOME"]).resolve(strict=False)
    for root in roots:
        assert root != home
        assert home not in root.parents or root != home
        assert root != Path("/")
