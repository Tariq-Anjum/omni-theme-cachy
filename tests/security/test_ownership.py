"""Ownership-policy tests (session 08), per the manifest ownership_policy.

The engine must reject — never repair — unsafe owners or permission bits,
checking after canonicalization and symlink resolution.
"""

from __future__ import annotations

import os
import stat

import pytest

from core import filesystem
from core.errors import PathPolicyError


def _target(tmp_path):
    target = tmp_path / "managed" / "file.conf"
    target.parent.mkdir(exist_ok=True)
    target.write_text("content\n")
    return target


def test_rejects_group_writable_file(tmp_path):
    target = _target(tmp_path)
    os.chmod(target, 0o664)
    mode_before = target.stat().st_mode
    with pytest.raises(PathPolicyError, match="group-writable"):
        filesystem.validate_write_target(target)
    assert target.stat().st_mode == mode_before  # never repaired


def test_rejects_world_writable_file(tmp_path):
    target = _target(tmp_path)
    os.chmod(target, 0o606)
    with pytest.raises(PathPolicyError, match="world-writable"):
        filesystem.validate_write_target(target)


def test_rejects_setuid_file(tmp_path):
    target = _target(tmp_path)
    os.chmod(target, 0o4755)
    with pytest.raises(PathPolicyError, match="setuid"):
        filesystem.validate_write_target(target)


def test_rejects_setgid_file(tmp_path):
    target = _target(tmp_path)
    os.chmod(target, 0o2755)
    with pytest.raises(PathPolicyError, match="setgid"):
        filesystem.validate_write_target(target)


def test_rejects_group_writable_parent_dir(tmp_path):
    target = _target(tmp_path)
    os.chmod(target.parent, 0o2775)
    with pytest.raises(PathPolicyError, match="group-writable"):
        filesystem.validate_write_target(target)


def test_rejects_world_writable_parent_without_sticky(tmp_path):
    target = _target(tmp_path)
    os.chmod(target.parent, 0o707)
    with pytest.raises(PathPolicyError, match="sticky"):
        filesystem.validate_write_target(target)


def test_accepts_world_writable_parent_with_sticky(tmp_path):
    target = _target(tmp_path)
    os.chmod(target.parent, 0o1707)
    assert filesystem.validate_write_target(target) == target.resolve()


def test_rejects_unsafe_owner_via_symlink(tmp_path):
    """The check applies after symlink resolution, not to the link itself."""
    target = _target(tmp_path)
    os.chmod(target, 0o606)
    link = tmp_path / "alias.conf"
    link.symlink_to(target)
    with pytest.raises(PathPolicyError, match="world-writable"):
        filesystem.validate_write_target(link)


@pytest.mark.skipif(os.geteuid() != 0, reason="wrong-owner needs root to construct")
def test_rejects_foreign_owner(tmp_path):
    target = _target(tmp_path)
    os.chown(target, 65534, 65534)
    with pytest.raises(PathPolicyError, match="owned by uid"):
        filesystem.validate_write_target(target)


def test_atomic_write_preserves_original_on_policy_violation(tmp_path):
    target = _target(tmp_path)
    os.chmod(target, 0o666)
    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(target, b"clobber\n")
    assert target.read_text() == "content\n"
    assert not stat.S_ISLNK(target.lstat().st_mode)
