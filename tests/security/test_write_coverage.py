"""Write-coverage tests (session 08): every managed write passes the gate.

``filesystem.atomic_write`` is the engine's only write primitive and calls
``validate_write_target`` internally; adapters and backup/restore helpers
route through the same validator. These tests assert the routing actually
happens on a full activation by recording every validated path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import filesystem
from core.activation import activate
from adapters import support as adapter_support


@pytest.fixture
def validator_recorder(monkeypatch):
    """Record every path passing through the central validator."""
    calls: list[Path] = []
    real_fs = filesystem.validate_write_target
    real_support = adapter_support.validate_write_target

    def recorder(path, **kwargs):
        calls.append(Path(path))
        return real_fs(path, **kwargs)

    monkeypatch.setattr(filesystem, "validate_write_target", recorder)
    monkeypatch.setattr(adapter_support, "validate_write_target", recorder)
    return calls


def test_every_managed_write_is_validated(sandbox, tmp_path, validator_recorder):
    outcome = activate(
        sandbox["theme"],
        registry_path=sandbox["registry"],
        templates_root=sandbox["templates_root"],
        state_root=tmp_path / "state",
    )
    assert outcome.ok, outcome.errors

    validated = {str(p) for p in validator_recorder}
    # every declared live target was validated
    for target in sandbox["targets"]:
        assert str(target) in validated, f"unvalidated write target: {target}"
    # every staged artifact and the staging manifest were validated
    # (recorded before promotion moved staging into generations/)
    staging = tmp_path / "state" / "staging"
    for artifact in ("app/one.conf", "app/two.conf", "manifest.json"):
        assert str(staging / artifact) in validated, (
            f"unvalidated staged write: {artifact}"
        )


def test_validator_is_invoked_by_atomic_write(tmp_path, monkeypatch):
    seen = []
    real = filesystem.validate_write_target

    def spy(path, **kwargs):
        seen.append(Path(path))
        return real(path, **kwargs)

    monkeypatch.setattr(filesystem, "validate_write_target", spy)
    target = tmp_path / "out" / "file.conf"
    filesystem.atomic_write(target, b"data\n")
    assert str(target) in {str(p) for p in seen}
    assert target.read_bytes() == b"data\n"
