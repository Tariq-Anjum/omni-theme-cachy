"""Symlink-safety tests (session 12).

Every scenario runs inside isolated tmp directories (``allow`` narrows
the approved roots to ``tmp_path/allowed``; everything else under
``tmp_path`` is genuinely outside the policy). The invariant under test:
no managed write ever follows a symlink out of an approved root, and no
symlink that appears between validation and replacement is followed.
"""

from __future__ import annotations

import pytest

from core import filesystem
from core.errors import PathPolicyError


# ---------------------------------------------------------------------------
# Target-component symlinks
# ---------------------------------------------------------------------------


def test_target_symlink_to_allowed_file_is_validated_and_followed(allow):
    """A link pointing *inside* a root passes policy: validation resolves
    it and the write lands on the resolved file (containment and the
    ownership policy were checked on that resolved path)."""
    allowed_file = allow / "real.conf"
    allowed_file.write_text("original\n")
    link = allow / "alias.conf"
    link.symlink_to(allowed_file)

    filesystem.atomic_write(link, b"new\n")

    assert link.is_symlink()  # the link itself is untouched
    assert allowed_file.read_text() == "new\n"
    assert link.read_text() == "new\n"


def test_target_symlink_to_outside_file_is_rejected(allow, tmp_path):
    victim = tmp_path / "victim.conf"
    victim.write_text("original\n")
    link = allow / "escape.conf"
    link.symlink_to(victim)

    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(link, b"clobber\n")

    assert victim.read_text() == "original\n"
    assert link.is_symlink()  # rejected write leaves the link in place
    assert not list(allow.glob(".*tmp"))


def test_parent_directory_symlink_is_rejected(allow, tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    link_dir = allow / "linked"
    link_dir.symlink_to(real_dir, target_is_directory=True)

    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(link_dir / "x.conf", b"data\n")

    assert list(real_dir.iterdir()) == []


def test_candidate_resolves_outside_root_via_intermediate_symlink(allow, tmp_path):
    outside = tmp_path / "outside-tree"
    (outside / "deep").mkdir(parents=True)
    link = allow / "hop"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathPolicyError):
        filesystem.validate_write_target(link / "deep" / "c.conf")
    assert not (outside / "deep" / "c.conf").exists()


# ---------------------------------------------------------------------------
# Broken / dangling symlinks
# ---------------------------------------------------------------------------


def test_broken_symlink_to_missing_inside_target_is_followed(allow):
    """A dangling link resolving inside a root is policy-legal: the write
    lands on the resolved path, and the link — still in place — now
    points at freshly written content instead of dangling."""
    dangling = allow / "dangling.conf"
    dangling.symlink_to(allow / "never-created.conf")

    filesystem.atomic_write(dangling, b"fresh\n")

    resolved = allow / "never-created.conf"
    assert resolved.is_file()
    assert resolved.read_text() == "fresh\n"
    assert dangling.is_symlink()
    assert dangling.read_text() == "fresh\n"


def test_broken_symlink_to_outside_is_rejected(allow, tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    dangling = allow / "dangling.conf"
    dangling.symlink_to(outside_dir / "missing.conf")

    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(dangling, b"data\n")

    assert dangling.is_symlink()
    assert list(outside_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# TOCTOU: a symlink that appears after the initial validation
# ---------------------------------------------------------------------------


def _swap_target_for_symlink_during_chmod(filesystem_module, monkeypatch, link, victim):
    """Simulate an attacker racing the write: immediately after the temp
    file is chmod'ed (i.e. after the initial validation), *link* becomes a
    symlink to *victim*. The policy re-check right before the replacement
    must catch it."""
    import os as _os

    real_chmod = filesystem_module.os.chmod

    def racing_chmod(path, mode):
        real_chmod(path, mode)
        link.symlink_to(victim)

    monkeypatch.setattr(filesystem_module.os, "chmod", racing_chmod)


def test_dangling_path_that_later_becomes_outside_symlink_is_rejected(
    allow, tmp_path, monkeypatch
):
    target = allow / "late.conf"
    victim = tmp_path / "victim.conf"
    victim.write_text("original\n")
    # Path is dangling-right-now legal; the symlink appears mid-write.
    _swap_target_for_symlink_during_chmod(
        filesystem, monkeypatch, target, victim
    )

    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(target, b"clobber\n")

    assert victim.read_text() == "original\n"
    assert target.is_symlink()
    assert not list(allow.glob(".*tmp"))


def test_path_that_later_becomes_inside_symlink_still_does_not_follow(
    allow, monkeypatch
):
    """Even a mid-write symlink pointing *inside* the root must not be
    followed: the pointed-to file keeps its bytes; the link is replaced."""
    pointed = allow / "pointed.conf"
    pointed.write_text("original\n")
    target = allow / "late.conf"
    _swap_target_for_symlink_during_chmod(
        filesystem, monkeypatch, target, pointed
    )

    filesystem.atomic_write(target, b"new\n")

    assert pointed.read_text() == "original\n"
    assert target.is_file() and not target.is_symlink()


def test_parent_directory_swapped_for_outside_symlink_mid_write_is_rejected(
    allow, tmp_path, monkeypatch
):
    """Racing the *parent* component: swapped for a symlink to an outside
    directory after validation, before replacement."""
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    sub = allow / "sub"
    sub.mkdir()
    target = sub / "f.conf"

    real_chmod = filesystem.os.chmod

    def racing_chmod(path, mode):
        real_chmod(path, mode)
        import shutil

        shutil.rmtree(sub)
        sub.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(filesystem.os, "chmod", racing_chmod)

    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(target, b"clobber\n")

    assert list(outside.iterdir()) == []
    assert not list(outside.glob(".*tmp"))
