"""Failure-injection, rollback and idempotency tests (session 08).

Every scenario uses deterministic injection (monkeypatched primitives or
filesystem modes) inside the sandbox — no real desktop paths, no network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core import filesystem
from core.adapters import AdapterRegistry
from core.activation import STATUS_FAILED, STATUS_ROLLED_BACK, activate, rollback
from core.errors import RollbackError
from core.state import (
    CURRENT_LINK,
    PREVIOUS_LINK,
    ensure_layout,
    generations_dir,
    switch_link,
    write_state,
    RuntimeState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(sandbox, tmp_path, *, adapters=None, theme=None, force=False):
    return activate(
        theme or sandbox["theme"],
        registry_path=sandbox["registry"],
        templates_root=sandbox["templates_root"],
        state_root=tmp_path / "state",
        adapters=adapters,
        force=force,
    )


def _target_bytes(target: Path) -> bytes | None:
    return target.read_bytes() if target.is_file() else None


# ---------------------------------------------------------------------------
# Atomic-write failures preserve the original
# ---------------------------------------------------------------------------


def test_read_only_destination_preserves_original(tmp_path):
    parent = tmp_path / "dest"
    parent.mkdir()
    original = parent / "keep.conf"
    original.write_bytes(b"original\n")
    os.chmod(parent, 0o555)  # not group/world-writable: passes the policy
    try:
        with pytest.raises(PermissionError):
            filesystem.atomic_write(original, b"clobber\n")
    finally:
        os.chmod(parent, 0o755)
    assert original.read_bytes() == b"original\n"
    assert [p.name for p in parent.iterdir()] == ["keep.conf"]


def test_missing_parent_dir_is_a_controlled_failure(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("i am a file\n")  # parent path occupied by a file
    with pytest.raises(OSError):
        filesystem.atomic_write(blocked / "sub" / "f.conf", b"x")
    assert blocked.read_text() == "i am a file\n"


def test_atomic_write_failure_keeps_previous_bytes(tmp_path, monkeypatch):
    target = tmp_path / "f.conf"
    filesystem.atomic_write(target, b"original\n")

    def boom(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(filesystem.os, "replace", boom)
    with pytest.raises(OSError):
        filesystem.atomic_write(target, b"clobber\n")
    assert target.read_bytes() == b"original\n"
    assert list(tmp_path.glob(".*tmp")) == []


# ---------------------------------------------------------------------------
# Malformed config: original not overwritten
# ---------------------------------------------------------------------------


def test_malformed_config_fails_before_writes(sandbox, tmp_path):
    first = _run(sandbox, tmp_path)
    assert first.ok
    target = sandbox["targets"][0]
    good = target.read_bytes()

    (sandbox["theme"] / "colors.toml").write_text('accent = "nothex"\n')
    second = _run(sandbox, tmp_path)
    assert second.status == STATUS_FAILED
    assert target.read_bytes() == good


# ---------------------------------------------------------------------------
# Partial failure: adapter-2 fails after adapter-1 succeeded
# ---------------------------------------------------------------------------


def test_critical_adapter_failure_after_core_success_rolls_back(
    sandbox, tmp_path, fake_adapter_factory
):
    first = _run(sandbox, tmp_path)
    assert first.ok
    target = sandbox["targets"][0]
    previous_bytes = target.read_bytes()
    # change the render so the idempotent short-circuit does not kick in
    tpl = sandbox["templates_root"] / "app" / "one.conf.tpl"
    tpl.write_text("one={{ accent }}\n# revised\n")

    ok, ok_critical = fake_adapter_factory("adapter-one")
    bad, bad_critical = fake_adapter_factory("adapter-two", fail_apply=True)
    registry = AdapterRegistry()
    registry.register(ok, critical=True)
    registry.register(bad, critical=True)

    outcome = _run(sandbox, tmp_path, adapters=registry)
    assert outcome.status == STATUS_ROLLED_BACK
    assert outcome.rollback_performed
    assert target.read_bytes() == previous_bytes


def test_rollback_failure_is_reported_and_state_left_unsafe(
    sandbox, tmp_path, fake_adapter_factory, monkeypatch
):
    """When even the rollback path fails, the outcome says FAILED loudly."""
    from core import activation as activation_module
    from core.errors import StateError

    ok, _ = fake_adapter_factory("adapter-one")
    bad, _ = fake_adapter_factory("adapter-two", fail_apply=True)
    registry = AdapterRegistry()
    registry.register(ok, critical=True)
    registry.register(bad, critical=True)

    def revert_boom(*args, **kwargs):
        raise StateError("injected pointer revert failure")

    monkeypatch.setattr(activation_module, "revert_to_state", revert_boom)
    outcome = _run(sandbox, tmp_path, adapters=registry)
    # the rollback was attempted but could not complete: reported FAILED
    # with the failure on the record (state must not be claimed safe)
    assert outcome.status == STATUS_FAILED
    assert outcome.rollback_performed  # attempted...
    assert any("pointer revert failed" in e for e in outcome.errors)  # ...and failed loudly


def test_interrupted_promotion_triggers_rollback(sandbox, tmp_path, monkeypatch):
    first = _run(sandbox, tmp_path)
    assert first.ok
    target = sandbox["targets"][0]
    previous_bytes = target.read_bytes()

    from core import state as state_module

    tpl = sandbox["templates_root"] / "app" / "one.conf.tpl"
    tpl.write_text("one={{ accent }}\n# revised\n")

    real_replace = state_module.os.replace
    crashed = {"done": False}

    def replace_boom(src, dst, *args, **kwargs):
        # crash the promotion itself, but let the rollback path through
        if Path(dst).name == CURRENT_LINK and not crashed["done"]:
            crashed["done"] = True
            raise OSError("injected crash during promotion")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(state_module.os, "replace", replace_boom)
    outcome = _run(sandbox, tmp_path)
    assert outcome.status == STATUS_ROLLED_BACK
    assert target.read_bytes() == previous_bytes


# ---------------------------------------------------------------------------
# Broken / missing current / previous pointers
# ---------------------------------------------------------------------------


def test_rollback_without_previous_generation_raises(sandbox, tmp_path):
    with pytest.raises(RollbackError):
        rollback(state_root=tmp_path / "state")


def test_rollback_with_vanished_previous_generation_raises(sandbox, tmp_path):
    assert _run(sandbox, tmp_path).ok
    # a second (changed) activation establishes a previous generation
    sandbox["templates_root"].joinpath("app/one.conf.tpl").write_text(
        "one={{ accent }}\n# revised\n"
    )
    assert _run(sandbox, tmp_path).ok
    root = tmp_path / "state"
    prev = Path(os.readlink(root / PREVIOUS_LINK)).name
    import shutil

    shutil.rmtree(generations_dir(root) / prev)
    with pytest.raises(RollbackError, match="gone"):
        rollback(state_root=root)


def test_dangling_current_link_is_not_silent_state(sandbox, tmp_path):
    _run(sandbox, tmp_path)
    root = tmp_path / "state"
    (root / CURRENT_LINK).unlink()
    (root / CURRENT_LINK).symlink_to("generations/gen-does-not-exist")
    from core.state import link_target

    # The pointer is structurally present but points nowhere usable;
    # promotion refuses to switch onto a missing generation.
    with pytest.raises(Exception):
        switch_link(root, CURRENT_LINK, "gen-does-not-exist")
    assert link_target(root, CURRENT_LINK) == "gen-does-not-exist"


def test_revert_to_state_removes_fresh_install_pointers(sandbox, tmp_path):
    root = ensure_layout(tmp_path / "state")
    (root / CURRENT_LINK).symlink_to("generations/gen-1")
    (root / PREVIOUS_LINK).symlink_to("generations/gen-0")
    write_state(
        root,
        RuntimeState(current_theme="x", current_generation="gen-1"),
    )
    from core.state import revert_to_state

    revert_to_state(root, RuntimeState())
    assert not (root / CURRENT_LINK).exists()
    assert not (root / PREVIOUS_LINK).exists()


# ---------------------------------------------------------------------------
# Idempotency: apply twice against an isolated temp root
# ---------------------------------------------------------------------------


def test_apply_is_idempotent(sandbox, tmp_path):
    root = tmp_path / "state"
    first = _run(sandbox, tmp_path)
    assert first.ok
    state_dir = tmp_path / "state"

    def snapshot():
        # staging/ is a scratch area re-rendered on every run by design;
        # everything else must be byte-identical.
        return {
            str(p.relative_to(state_dir)): filesystem.sha256_file(p)
            for p in sorted(state_dir.rglob("*"))
            if p.is_file() and p.name != "state.json" and "staging" not in p.parts
        }

    before = snapshot()
    generations_before = sorted(p.name for p in (state_dir / "generations").iterdir())
    targets_before = [_target_bytes(t) for t in sandbox["targets"]]

    second = _run(sandbox, tmp_path)
    assert second.ok
    assert second.generation == first.generation  # short-circuit, no new gen
    assert sorted(p.name for p in (state_dir / "generations").iterdir()) == (
        generations_before
    )
    assert snapshot() == before
    assert [_target_bytes(t) for t in sandbox["targets"]] == targets_before
    # no stray temp files anywhere in the state tree
    assert [p for p in state_dir.rglob(".*tmp")] == []
