"""Integration tests for session 04: activation, promotion, rollback, dry run.

Everything runs inside an isolated ``fake_home``: XDG roots, state tree,
targets and themes all live under ``tmp_path``. No test touches the real
``$HOME``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from core import filesystem
from core.adapters import AdapterCapability, AdapterRegistry, AdapterResult
from core.engine import ThemeEngine
from core.errors import RollbackError
from core.events import (
    EVENT_POST_ACTIVATE,
    EVENT_POST_CORE_ACTIVATE,
    EVENT_POST_ROLLBACK,
    EVENT_POST_VERIFY,
    EVENT_PRE_ACTIVATE,
    EVENT_PRE_ROLLBACK,
    LIFECYCLE_EVENTS,
    EventDispatcher,
)
from core.state import (
    STATE_FILE,
    read_state,
)
from conftest import FULL_PALETTE

# ---------------------------------------------------------------------------
# Fixtures and stubs
# ---------------------------------------------------------------------------

REGISTRY_TWO = """
[[template]]
adapter = "kde-colorscheme"

[template.source]
path = "kde/test.colors.tpl"

[template.target]
path = "~/.local/share/color-schemes/Test.colors"

[[template]]
[template.source]
path = "term/foot.ini.tpl"

[template.target]
path = "~/.config/foot/foot.ini"
"""


def _theme_toml(theme_id: str, name: str) -> str:
    return (
        "[theme]\n"
        f'name = "{name}"\n'
        f'id = "{theme_id}"\n'
        "version = 1\n"
        'mode = "dark"\n'
        "\n[wallpaper]\n"
        'default = "wallpapers/test.png"\n'
    )


class StubAdapter:
    """Contract-conforming adapter with injectable failure modes."""

    def __init__(
        self,
        id: str = "stub",
        *,
        supported: bool = True,
        reason: str | None = None,
        version: str | None = None,
        critical: bool = False,
        fail_apply: bool = False,
        fail_verify: bool = False,
        fail_rollback: bool = False,
    ) -> None:
        self.id = id
        self.critical = critical
        self.supported = supported
        self.reason = reason
        self.version = version
        self.fail_apply = fail_apply
        self.fail_verify = fail_verify
        self.fail_rollback = fail_rollback
        self.calls: list[tuple] = []
        self.events: list = []

    def capability(self, context) -> AdapterCapability:
        self.calls.append(("capability",))
        return AdapterCapability(
            id=self.id, supported=self.supported, reason=self.reason, version=self.version
        )

    def plan(self, resolved_theme, context):
        self.calls.append(("plan",))
        return {"theme": resolved_theme.meta.id}

    def render(self, resolved_theme, staging, context):
        self.calls.append(("render",))

    def apply(self, plan, context) -> AdapterResult:
        self.calls.append(("apply",))
        if self.fail_apply:
            raise RuntimeError("boom")
        return AdapterResult(adapter_id=self.id, applied=True)

    def verify(self, plan, context) -> AdapterResult:
        self.calls.append(("verify",))
        if self.fail_verify:
            return AdapterResult(
                adapter_id=self.id, applied=True, verified=False,
                errors=("verification mismatch",),
            )
        return AdapterResult(adapter_id=self.id, verified=True)

    def rollback(self, previous_state, context) -> AdapterResult:
        self.calls.append(("rollback",))
        if self.fail_rollback:
            raise RuntimeError("cannot revert")
        return AdapterResult(adapter_id=self.id, rolled_back=True)


@pytest.fixture
def world(tmp_path, make_theme, fake_home):
    """Templates, registry, two themes and an isolated state root."""
    templates = tmp_path / "templates"
    (templates / "kde").mkdir(parents=True)
    (templates / "term").mkdir(parents=True)
    (templates / "kde" / "test.colors.tpl").write_text(
        "# rendered by omni-theme\n"
        "Accent={{ accent }}\n"
    )
    (templates / "term" / "foot.ini.tpl").write_text(
        "foreground={{ foreground }}\ncursor={{ color7_strip }}\n"
    )
    registry = templates / "targets.toml"
    registry.write_text(REGISTRY_TWO)

    themes_root = tmp_path / "themes"
    alpha = make_theme(
        name="themes/alpha",
        theme_toml=_theme_toml("alpha", "Alpha"),
    )
    beta = make_theme(
        name="themes/beta",
        theme_toml=_theme_toml("beta", "Beta"),
        colors={"accent": "#c96442"},
    )
    for theme_dir in (alpha, beta):
        wall = theme_dir / "wallpapers"
        wall.mkdir(exist_ok=True)
        (wall / "test.png").touch()

    return {
        "templates_root": templates,
        "registry": registry,
        "themes_root": themes_root,
        "alpha": alpha,
        "beta": beta,
        "state_root": fake_home / ".local" / "state" / "omni-theme",
        "target_colors": fake_home / ".local" / "share" / "color-schemes" / "Test.colors",
        "target_foot": fake_home / ".config" / "foot" / "foot.ini",
    }


def engine_for(world, *, adapters=None, dispatcher=None) -> ThemeEngine:
    return ThemeEngine(
        themes_root=world["themes_root"],
        registry_path=world["registry"],
        templates_root=world["templates_root"],
        state_root=world["state_root"],
        adapters=adapters,
        dispatcher=dispatcher,
    )


def recording_dispatcher():
    dispatcher = EventDispatcher()
    names: list[str] = []
    for name in LIFECYCLE_EVENTS:
        dispatcher.subscribe(name, lambda event: names.append(event.name))
    return dispatcher, names


def generations(world) -> list[str]:
    gens = world["state_root"] / "generations"
    if not gens.is_dir():
        return []
    return sorted(p.name for p in gens.iterdir())


# ---------------------------------------------------------------------------
# First activation
# ---------------------------------------------------------------------------


class TestFirstActivation:
    def test_creates_generation_pointers_state_and_targets(self, world):
        engine = engine_for(world)

        outcome = engine.apply("alpha")

        assert outcome.ok and outcome.status == "VERIFIED"
        assert outcome.phase == "VERIFIED"
        assert outcome.core_changed is True
        assert outcome.theme_id == "alpha"

        # immutable generation exists and is complete
        assert len(generations(world)) == 1
        gen_dir = world["state_root"] / "generations" / outcome.generation
        assert (gen_dir / "manifest.json").is_file()
        assert (gen_dir / "kde" / "test.colors").is_file()

        # atomic relative symlinks, no leftover temp links
        current = world["state_root"] / "current"
        assert current.is_symlink()
        assert os.readlink(current) == f"generations/{outcome.generation}"
        assert not (world["state_root"] / ".current.new").exists()

        # owned external targets materialized byte-exact
        rendered = (gen_dir / "kde" / "test.colors").read_text()
        assert rendered == (
            f"# rendered by omni-theme\nAccent={FULL_PALETTE['accent']}\n"
        )
        assert world["target_colors"].read_text() == rendered
        assert "cursor=c5cbd6" in world["target_foot"].read_text()

        # persisted state describes the new reality
        state = read_state(world["state_root"])
        assert state.current_theme == "alpha"
        assert state.previous_theme is None
        assert state.previous_generation is None
        assert state.current_generation == outcome.generation
        targets = {m.target for m in state.managed_targets}
        assert str(world["target_colors"]) in targets
        record = next(
            m for m in state.managed_targets if m.target == str(world["target_colors"])
        )
        assert record.hash == filesystem.sha256_file(world["target_colors"])

    def test_status_reports_consistent_runtime(self, world):
        engine = engine_for(world)
        engine.apply("alpha")

        status = engine.status()

        assert status.state_exists is True
        assert status.current_theme == "alpha"
        assert status.consistent is True
        assert status.details == ()
        assert status.managed_targets == 2


# ---------------------------------------------------------------------------
# Second activation / idempotency
# ---------------------------------------------------------------------------


class TestSecondActivation:
    def test_promotes_new_generation_and_displaces_previous(self, world):
        engine = engine_for(world)
        first = engine.apply("alpha")
        old_gen_dir = world["state_root"] / "generations" / first.generation

        second = engine.apply("beta")

        assert second.status == "VERIFIED"
        assert second.core_changed is True
        assert second.generation != first.generation

        state = read_state(world["state_root"])
        assert state.current_theme == "beta"
        assert state.previous_theme == "alpha"
        assert state.current_generation == second.generation
        assert state.previous_generation == first.generation

        # old generation kept for rollback, pointer chain correct
        assert old_gen_dir.is_dir()
        assert len(generations(world)) == 2

        colors = world["target_colors"].read_text()
        assert colors == f"# rendered by omni-theme\nAccent=#c96442\n"


class TestIdempotency:
    def test_repeated_same_theme_keeps_generation(self, world):
        engine = engine_for(world)
        first = engine.apply("alpha")
        before = read_state(world["state_root"])

        again = engine.apply("alpha")

        assert again.status == "VERIFIED"
        assert again.core_changed is False
        assert again.generation == first.generation
        assert len(generations(world)) == 1
        assert any("identical content" in w for w in again.warnings)

        # state is byte-for-byte semantically identical (timestamp kept)
        assert read_state(world["state_root"]) == before

    def test_repeated_activation_re_runs_adapters(self, world):
        registry = AdapterRegistry()
        stub = StubAdapter("stub")
        registry.register(stub)
        engine = engine_for(world, adapters=registry)

        engine.apply("alpha")
        engine.apply("alpha")

        assert stub.calls.count(("apply",)) == 2  # idempotent-by-contract rerun


# ---------------------------------------------------------------------------
# Conflicts (ownership-aware)
# ---------------------------------------------------------------------------


class TestConflicts:
    def test_untracked_user_file_blocks_first_activation(self, world):
        world["target_colors"].parent.mkdir(parents=True)
        world["target_colors"].write_text("# precious hand-made config\n")

        engine = engine_for(world)
        outcome = engine.apply("alpha")

        assert outcome.status == "FAILED"
        assert len(outcome.conflicts) == 1
        assert outcome.conflicts[0].target == world["target_colors"]
        assert outcome.conflicts[0].managed_hash == ""  # never engine-owned

        # absolutely nothing mutated
        assert world["target_colors"].read_text() == "# precious hand-made config\n"
        assert not (world["state_root"] / "current").exists()
        assert not (world["state_root"] / STATE_FILE).exists()
        assert generations(world) == []

    def test_user_modified_owned_file_blocks_second_activation(self, world):
        engine = engine_for(world)
        first = engine.apply("alpha")
        world["target_colors"].write_text("# my tweaks\n")
        state_bytes = (world["state_root"] / STATE_FILE).read_bytes()

        outcome = engine.apply("beta")

        assert outcome.status == "FAILED"
        assert outcome.conflicts[0].target == world["target_colors"]

        # live mutation never happened: pointer and file untouched
        current = world["state_root"] / "current"
        assert Path(os.readlink(current)).name == first.generation
        assert world["target_colors"].read_text() == "# my tweaks\n"
        assert (world["state_root"] / STATE_FILE).read_bytes() == state_bytes

    def test_force_overrides_conflicts_and_warns(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        world["target_colors"].write_text("# my tweaks\n")

        outcome = engine.apply("beta", force=True)

        assert outcome.status == "VERIFIED"
        assert any("forced overwrite" in w for w in outcome.warnings)
        assert "Accent=#c96442" in world["target_colors"].read_text()


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_mutates_nothing_and_cleans_sandbox(self, world):
        engine = engine_for(world)

        outcome = engine.apply("alpha", dry_run=True)

        assert outcome.status == "DRY_RUN"
        assert outcome.dry_run is True
        assert outcome.core_changed is False
        assert outcome.generation is None
        assert not (world["state_root"] / STATE_FILE).exists()
        assert not (world["state_root"] / "current").exists()
        assert generations(world) == []
        assert not world["target_colors"].exists()
        leftovers = [
            p.name
            for p in world["state_root"].iterdir()
            if p.name.startswith(".dryrun-")
        ]
        assert leftovers == []

    def test_dry_run_reports_capabilities_and_conflicts(self, world):
        world["target_foot"].parent.mkdir(parents=True, exist_ok=True)
        world["target_foot"].write_text("user-edited\n")
        registry = AdapterRegistry()
        registry.register(StubAdapter("kde"))
        registry.register(StubAdapter("gtk", supported=False, reason="no gnome"))
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha", dry_run=True)

        caps = {c.id: c for c in outcome.capabilities}
        assert caps["kde"].supported is True
        assert caps["gtk"].supported is False
        assert caps["gtk"].reason == "no gnome"
        assert len(outcome.conflicts) == 1
        assert outcome.conflicts[0].managed_hash == ""

    def test_dry_run_emits_no_events(self, world):
        dispatcher, names = recording_dispatcher()
        engine = engine_for(world, dispatcher=dispatcher)

        engine.apply("alpha", dry_run=True)

        assert names == []

    def test_dry_run_leaves_active_state_untouched(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        state_bytes = (world["state_root"] / STATE_FILE).read_bytes()
        current_target = os.readlink(world["state_root"] / "current")

        engine.apply("beta", dry_run=True)

        assert (world["state_root"] / STATE_FILE).read_bytes() == state_bytes
        assert os.readlink(world["state_root"] / "current") == current_target
        assert len(generations(world)) == 1  # still only alpha's generation


# ---------------------------------------------------------------------------
# Adapter execution semantics
# ---------------------------------------------------------------------------


class TestAdapterSemantics:
    def test_unsupported_adapter_does_not_fail_activation(self, world):
        registry = AdapterRegistry()
        registry.register(StubAdapter("gtk", supported=False, reason="gnome absent"))
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "VERIFIED"  # unsupported != failure
        result = outcome.adapter_results[0]
        assert result.attempted is False
        assert result.supported is False
        cap = outcome.capabilities[0]
        assert cap.supported is False and cap.reason == "gnome absent"
        assert world["target_colors"].exists()  # core work still done

    def test_non_critical_failure_degrades_but_promotes(self, world):
        registry = AdapterRegistry()
        registry.register(StubAdapter("flaky", fail_apply=True))
        healthy = StubAdapter("healthy")
        registry.register(healthy)
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "DEGRADED"
        assert outcome.phase == "ADAPTERS_APPLIED"
        # core promotion survived
        state = read_state(world["state_root"])
        assert state.current_theme == "alpha"
        assert world["target_colors"].is_file()
        # failure captured, later adapters still ran
        flaky = outcome.adapter_results[0]
        assert flaky.applied is False
        assert any("boom" in e for e in flaky.errors)
        assert ("apply",) in healthy.calls

    def test_non_critical_verify_failure_degrades(self, world):
        registry = AdapterRegistry()
        registry.register(StubAdapter("shaky", fail_verify=True))
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "DEGRADED"
        result = outcome.adapter_results[0]
        assert result.applied is True and result.verified is False
        assert "verification mismatch" in result.errors

    def test_critical_failure_after_promotion_rolls_back(self, world):
        registry = AdapterRegistry()
        critical = StubAdapter("critical-kde", critical=True)
        registry.register(critical)
        engine = engine_for(world, adapters=registry)

        first = engine.apply("alpha")
        alpha_content = world["target_colors"].read_text()
        before_state = read_state(world["state_root"])

        critical.fail_apply = True  # the next activation goes sideways
        outcome = engine.apply("beta")

        assert outcome.status == "ROLLED_BACK"
        assert outcome.rollback_performed is True
        assert any("critical adapter critical-kde" in e for e in outcome.errors)

        # pointers and content restored to alpha's generation
        current = world["state_root"] / "current"
        assert Path(os.readlink(current)).name == first.generation
        assert world["target_colors"].read_text() == alpha_content
        assert ("rollback",) in critical.calls

        # state.json was never advanced to beta
        after = read_state(world["state_root"])
        assert after == before_state

    def test_critical_verification_failure_rolls_back(self, world):
        registry = AdapterRegistry()
        registry.register(StubAdapter("critical-x", critical=True, fail_verify=True))
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "ROLLED_BACK"
        assert outcome.adapter_results[0].verified is False
        assert not (world["state_root"] / "current").exists()
        assert not world["target_colors"].exists()  # engine-owned file removed

    def test_first_activation_critical_failure_leaves_clean_slate(self, world):
        registry = AdapterRegistry()
        stub = StubAdapter("critical-a", critical=True, fail_apply=True)
        registry.register(stub)
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "ROLLED_BACK"
        assert not (world["state_root"] / "current").exists()
        assert not (world["state_root"] / "previous").exists()
        assert not (world["state_root"] / STATE_FILE).exists()
        assert not world["target_colors"].exists()
        assert not world["target_foot"].exists()
        assert ("rollback",) in stub.calls

    def test_failed_adapter_rollback_is_reported_as_failure(self, world):
        registry = AdapterRegistry()
        critical = StubAdapter("critical-b", critical=True)
        registry.register(critical)
        engine = engine_for(world, adapters=registry)
        first = engine.apply("alpha")

        critical.fail_apply = True
        critical.fail_rollback = True
        outcome = engine.apply("beta")

        # pointers were still reverted before the broken adapter rollback
        current = world["state_root"] / "current"
        assert Path(os.readlink(current)).name == first.generation
        assert outcome.status == "FAILED"
        assert outcome.rollback_performed is True
        assert any("cannot revert" in e for e in outcome.errors)

    def test_unsupported_then_supported_mixed_registry(self, world):
        registry = AdapterRegistry()
        registry.register(StubAdapter("gtk", supported=False))
        registry.register(StubAdapter("term"))
        engine = engine_for(world, adapters=registry)

        outcome = engine.apply("alpha")

        assert outcome.status == "VERIFIED"
        assert [r.attempted for r in outcome.adapter_results] == [False, True]


# ---------------------------------------------------------------------------
# Explicit rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def test_rollback_restores_previous_generation_and_files(self, world):
        dispatcher, names = recording_dispatcher()
        engine = engine_for(world, dispatcher=dispatcher)
        first = engine.apply("alpha")
        alpha_rendered = (
            world["state_root"] / "generations" / first.generation / "kde" / "test.colors"
        ).read_text()
        engine.apply("beta")

        outcome = engine.rollback()

        assert outcome.status == "ROLLED_BACK"
        assert outcome.rollback_performed is True
        assert outcome.theme_id == "alpha"

        state = read_state(world["state_root"])
        assert state.current_theme == "alpha"
        assert state.previous_theme == "beta"
        assert state.current_generation == first.generation
        assert state.previous_generation != first.generation

        assert Path(os.readlink(world["state_root"] / "current")).name == (
            first.generation
        )
        assert world["target_colors"].read_text() == alpha_rendered

        # ownership records updated to the restored content
        record = next(
            m for m in state.managed_targets if m.target == str(world["target_colors"])
        )
        assert record.hash == filesystem.sha256_file(world["target_colors"])
        assert names[-2:] == [EVENT_PRE_ROLLBACK, EVENT_POST_ROLLBACK]

    def test_double_rollback_swaps_back_to_beta(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        engine.apply("beta")

        engine.rollback()
        again = engine.rollback()

        assert again.theme_id == "beta"
        assert engine.current_theme() == "beta"
        assert engine.previous_theme() == "alpha"
        assert "Accent=#c96442" in world["target_colors"].read_text()

    def test_missing_previous_generation_raises(self, world):
        engine = engine_for(world)
        with pytest.raises(RollbackError, match="no previous generation"):
            engine.rollback()

    def test_stale_previous_generation_raises(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        engine.apply("beta")
        stale_gen = read_state(world["state_root"]).previous_generation
        shutil.rmtree(world["state_root"] / "generations" / stale_gen)

        with pytest.raises(RollbackError, match="stale"):
            engine.rollback()

        # nothing moved
        assert engine.current_theme() == "beta"

    def test_corrupt_previous_manifest_raises(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        engine.apply("beta")
        prev_gen = read_state(world["state_root"]).previous_generation
        (world["state_root"] / "generations" / prev_gen / "manifest.json").unlink()

        with pytest.raises(RollbackError, match="manifest"):
            engine.rollback()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class TestEventLifecycle:
    def test_successful_apply_emits_expected_sequence(self, world):
        dispatcher, names = recording_dispatcher()
        engine = engine_for(world, dispatcher=dispatcher)

        engine.apply("alpha")

        assert names == [
            EVENT_PRE_ACTIVATE,
            EVENT_POST_CORE_ACTIVATE,
            EVENT_POST_VERIFY,
            EVENT_POST_ACTIVATE,
        ]

    def test_subscriber_failure_becomes_warning_not_breakage(self, world):
        dispatcher = EventDispatcher()

        def boom(event):
            raise RuntimeError("observer broke")

        dispatcher.subscribe(EVENT_PRE_ACTIVATE, boom, owner="bad-observer")
        engine = engine_for(world, dispatcher=dispatcher)

        outcome = engine.apply("alpha")

        assert outcome.status == "VERIFIED"
        assert any("bad-observer" in w for w in outcome.warnings)


# ---------------------------------------------------------------------------
# Engine introspection
# ---------------------------------------------------------------------------


class TestEngineIntrospection:
    def test_theme_accessors_track_transitions(self, world):
        engine = engine_for(world)
        assert engine.current_theme() is None
        assert engine.previous_theme() is None

        engine.apply("alpha")
        engine.apply("beta")

        assert engine.current_theme() == "beta"
        assert engine.previous_theme() == "alpha"

    def test_status_detects_pointer_drift(self, world):
        engine = engine_for(world)
        engine.apply("alpha")
        assert engine.status().consistent is True

        (world["state_root"] / "current").unlink()

        status = engine.status()
        assert status.consistent is False
        assert any("current" in d for d in status.details)

    def test_apply_theme_alias_matches_apply(self, world):
        engine = engine_for(world)
        via_alias = engine.apply_theme("alpha", dry_run=True)
        assert via_alias.status == "DRY_RUN"
