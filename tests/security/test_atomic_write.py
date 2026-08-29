"""Atomic-write and atomic-copy behavior tests (session 12).

Complements the session-08 failure/rollback tests with the contract
details: temp-sibling strategy, permission semantics, the copy primitive,
and temp-file hygiene on every failure path.
"""

from __future__ import annotations

import os
import stat

import pytest

from core import filesystem
from core.errors import PathPolicyError


# ---------------------------------------------------------------------------
# Permission semantics
# ---------------------------------------------------------------------------


def test_new_file_gets_default_mode(tmp_path):
    target = tmp_path / "fresh.conf"
    filesystem.atomic_write(target, b"data\n")
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_explicit_mode_is_applied(tmp_path):
    target = tmp_path / "secret.conf"
    filesystem.atomic_write(target, b"data\n", mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_existing_mode_is_preserved_across_rewrite(tmp_path):
    target = tmp_path / "tweaked.conf"
    filesystem.atomic_write(target, b"v1\n")
    os.chmod(target, 0o600)
    filesystem.atomic_write(target, b"v2\n")
    assert target.read_text() == "v2\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_text_uses_utf8_and_mode_argument(tmp_path):
    target = tmp_path / "text.conf"
    returned = filesystem.atomic_write_text(target, "café\n", mode=0o640)
    assert returned == target
    assert target.read_text(encoding="utf-8") == "café\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


# ---------------------------------------------------------------------------
# Temp-sibling hygiene
# ---------------------------------------------------------------------------


def test_no_temp_sibling_survives_a_successful_write(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    target = workdir / "clean.conf"
    filesystem.atomic_write(target, b"data\n")
    assert [p.name for p in workdir.iterdir()] == ["clean.conf"]


def test_revalidation_failure_removes_temp_sibling(tmp_path, monkeypatch):
    """A rejection at the pre-replace re-check must not leave debris."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    target = workdir / "guard.conf"
    filesystem.atomic_write(target, b"original\n")

    real = filesystem.validate_write_target
    calls = {"n": 0}

    def flaky(path, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:  # the re-check inside the install path
            raise PathPolicyError("injected re-check rejection")
        return real(path, **kwargs)

    monkeypatch.setattr(filesystem, "validate_write_target", flaky)
    with pytest.raises(PathPolicyError):
        filesystem.atomic_write(target, b"clobber\n")
    assert [p.name for p in workdir.iterdir()] == ["guard.conf"]
    assert target.read_bytes() == b"original\n"


# ---------------------------------------------------------------------------
# atomic_copy
# ---------------------------------------------------------------------------


def test_atomic_copy_installs_source_bytes(tmp_path):
    source = tmp_path / "src.bin"
    source.write_bytes(b"\x89PNG\r\n\x1a\npayload")
    target = tmp_path / "dst" / "copy.bin"

    returned = filesystem.atomic_copy(source, target)

    assert returned == target
    assert target.read_bytes() == source.read_bytes()


def test_atomic_copy_preserves_existing_target_mode(tmp_path):
    source = tmp_path / "src"
    source.write_bytes(b"v2\n")
    target = tmp_path / "dst"
    filesystem.atomic_write(target, b"v1\n", mode=0o600)

    filesystem.atomic_copy(source, target)

    assert target.read_bytes() == b"v2\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_copy_rejects_target_outside_approved_roots(allow, tmp_path):
    source = tmp_path / "src"
    source.write_bytes(b"x\n")
    outside = tmp_path / "outside.conf"

    with pytest.raises(PathPolicyError):
        filesystem.atomic_copy(source, outside)

    assert not outside.exists()


def test_atomic_copy_missing_source_leaves_target_untouched(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    target = workdir / "keep.conf"
    filesystem.atomic_write(target, b"precious\n")

    with pytest.raises(OSError):
        filesystem.atomic_copy(tmp_path / "missing.src", target)

    assert target.read_bytes() == b"precious\n"
    assert [p.name for p in workdir.iterdir()] == ["keep.conf"]


def test_atomic_copy_rejects_unsafe_existing_target(tmp_path):
    source = tmp_path / "src"
    source.write_bytes(b"x\n")
    target = tmp_path / "unsafe.conf"
    target.write_text("user data\n")
    os.chmod(target, 0o666)

    with pytest.raises(PathPolicyError):
        filesystem.atomic_copy(source, target)

    assert target.read_text() == "user data\n"  # never repaired, never clobbered
