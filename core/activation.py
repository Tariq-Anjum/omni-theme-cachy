"""Activation pipeline: staging → promotion → adapters → verification.

Consumes the session-03 staging pipeline and turns rendered output into
managed runtime state (see :mod:`core.state` for the layout and the
atomic-promotion primitive)::

    resolve → merge overlay → validate → render → validate output
      → stage → inspect managed conflicts → snapshot current metadata
      → prepare new generation → atomically promote generation
      → materialize owned targets → apply adapters → verify
      → persist state

Failure policy (encoded here, never improvised by callers):

* staging/validation/conflict problems happen **before any live
  mutation** and yield a FAILED outcome with untouched state;
* an explicit ``force`` flag is the only way past user-modified
  targets, and every forced overwrite is reported as a warning;
* core promotion/materialization failures are critical ⇒ deterministic
  rollback to the pre-activation state;
* unsupported adapters are skipped and reported — they never fail the
  activation;
* non-critical adapter failures mark the outcome DEGRADED and
  processing continues; critical ones stop the loop and roll back;
* success is claimed only after byte-level verification of everything
  the engine wrote.

Dry runs execute the read-only prefix of this pipeline against a
temporary staging sandbox: manifests, conflicts and adapter
capabilities are reported, but no external file, pointer, or persisted
state changes and no lifecycle events are emitted.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core import filesystem
from core.adapters import (
    AdapterCapability,
    AdapterRegistry,
    AdapterResult,
)
from core.errors import ActivationError, RollbackError, StateError, ThemeError
from core.events import (
    EVENT_POST_ACTIVATE,
    EVENT_POST_CORE_ACTIVATE,
    EVENT_POST_ROLLBACK,
    EVENT_POST_VERIFY,
    EVENT_PRE_ACTIVATE,
    EVENT_PRE_ROLLBACK,
    EventDispatcher,
)
from core.state import (
    ManagedTarget,
    CURRENT_LINK,
    PREVIOUS_LINK,
    RuntimeState,
    ensure_layout,
    generation_dir,
    inspect_managed_conflicts,
    load_generation_manifest,
    manifest_hash_map,
    new_generation_id,
    promote_generation,
    read_state,
    revert_to_state,
    switch_link,
    utc_now_iso,
    write_state,
)
from core.staging import (
    Manifest,
    StageResult,
    load_manifest,
    stage_theme,
)
from core.theme_loader import load_theme_with_overlay
from core.validation import validate_theme

__all__ = [
    "PHASE_CORE_STAGED",
    "PHASE_CORE_PROMOTED",
    "PHASE_ADAPTERS_APPLIED",
    "PHASE_VERIFIED",
    "STATUS_VERIFIED",
    "STATUS_DEGRADED",
    "STATUS_FAILED",
    "STATUS_ROLLED_BACK",
    "STATUS_DRY_RUN",
    "ActivationContext",
    "ActivationOutcome",
    "verify_staged_integrity",
    "activate",
    "rollback",
]

# Lifecycle phases (how far an activation got).
PHASE_CORE_STAGED = "CORE_STAGED"
PHASE_CORE_PROMOTED = "CORE_PROMOTED"
PHASE_ADAPTERS_APPLIED = "ADAPTERS_APPLIED"
PHASE_VERIFIED = "VERIFIED"

# Final verdicts.
STATUS_VERIFIED = "VERIFIED"
STATUS_DEGRADED = "DEGRADED"
STATUS_FAILED = "FAILED"
STATUS_ROLLED_BACK = "ROLLED_BACK"
STATUS_DRY_RUN = "DRY_RUN"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivationContext:
    """Everything an adapter may need during one activation."""

    state_root: Path
    #: Promoted artifact tree for this activation (read-only for adapters).
    generation_dir: Path
    manifest: Manifest
    #: Merged (overlay-applied) theme; None in some rollback contexts.
    theme: object | None
    dry_run: bool
    #: State snapshot taken before this activation began.
    previous_state: RuntimeState


@dataclass(frozen=True)
class ActivationOutcome:
    """What one apply/rollback actually did."""

    status: str
    phase: str | None
    theme_id: str | None = None
    theme_name: str | None = None
    theme_source: Path | None = None
    generation: str | None = None
    previous_generation: str | None = None
    core_changed: bool = False
    dry_run: bool = False
    rollback_performed: bool = False
    #: Every live target the render pipeline plans to write (dry runs only).
    planned_targets: tuple = ()
    conflicts: tuple = ()
    capabilities: tuple[AdapterCapability, ...] = ()
    adapter_results: tuple[AdapterResult, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_VERIFIED, STATUS_DEGRADED, STATUS_ROLLED_BACK, STATUS_DRY_RUN)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "phase": self.phase,
            "theme_id": self.theme_id,
            "theme_name": self.theme_name,
            "theme_source": str(self.theme_source) if self.theme_source else None,
            "generation": self.generation,
            "previous_generation": self.previous_generation,
            "core_changed": self.core_changed,
            "dry_run": self.dry_run,
            "rollback_performed": self.rollback_performed,
            "planned_targets": [
                {
                    "target": str(t.get("target")),
                    "name": t.get("name"),
                    "adapter": t.get("adapter"),
                }
                for t in self.planned_targets
            ],
            "conflicts": [
                {
                    "target": str(c.target),
                    "managed_hash": c.managed_hash,
                    "actual_hash": c.actual_hash,
                }
                for c in self.conflicts
            ],
            "capabilities": [
                {
                    "id": c.id,
                    "supported": c.supported,
                    "reason": c.reason,
                    "version": c.version,
                }
                for c in self.capabilities
            ],
            "adapter_results": [r.to_dict() for r in self.adapter_results],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _outcome(
    status: str,
    *,
    phase: str | None = None,
    warnings=(),
    errors=(),
    **kwargs,
) -> ActivationOutcome:
    return ActivationOutcome(
        status=status, phase=phase, warnings=tuple(warnings), errors=tuple(errors), **kwargs
    )


# ---------------------------------------------------------------------------
# Core verification helpers
# ---------------------------------------------------------------------------


def verify_staged_integrity(stage_result: StageResult) -> None:
    """Re-hash every staged artifact against its manifest record.

    Raises :class:`ActivationError` naming the first mismatch; a staged
    tree that cannot trust itself must never be promoted.
    """
    for staged_file in stage_result.files:
        path = stage_result.staging_dir / staged_file.staged
        actual = filesystem.sha256_file(path)
        if actual != staged_file.hash:
            raise ActivationError(
                f"staged output failed integrity check: {path} hashes to "
                f"{actual}, manifest records {staged_file.hash}"
            )


def _manifest_of(stage_result: StageResult) -> Manifest:
    return load_manifest(stage_result.manifest_path)


def _materialize_targets(manifest: Manifest, generation_dir_path: Path) -> list[str]:
    """Copy promoted artifacts onto their declared live destinations."""
    errors: list[str] = []
    for entry in manifest.files:
        source = generation_dir_path / Path(entry.staged)
        try:
            data = source.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read promoted artifact {source}: {exc}")
            continue
        try:
            filesystem.atomic_write(Path(entry.target).expanduser(), data)
        except OSError as exc:
            errors.append(f"cannot write target {entry.target}: {exc}")
    return errors


def _verify_targets(manifest: Manifest) -> list[str]:
    """Byte-level confirmation that every written target matches the plan."""
    errors: list[str] = []
    for entry in manifest.files:
        target = Path(entry.target).expanduser()
        try:
            actual = filesystem.sha256_file(target)
        except FileNotFoundError:
            errors.append(f"target missing after apply: {target}")
            continue
        except OSError as exc:
            errors.append(f"cannot read target {target}: {exc}")
            continue
        if actual != entry.hash:
            errors.append(
                f"verification failed for {target}: content hash {actual}, "
                f"expected {entry.hash}"
            )
    return errors


def _merged_managed(state: RuntimeState, manifest: Manifest) -> tuple:
    """Old ownership records updated with everything this manifest wrote.

    Records for targets that dropped out of the manifest are kept: the
    engine still owns those files, and their last-written hashes are
    what future conflict checks must compare against.
    """
    merged = dict(state.managed_map)
    for entry in manifest.files:
        merged[str(Path(entry.target).expanduser())] = ManagedTarget(
            target=str(Path(entry.target).expanduser()),
            hash=entry.hash,
            name=entry.name,
            adapter=entry.adapter,
        )
    return tuple(sorted(merged.values(), key=lambda m: m.target))


def _emit(dispatcher: EventDispatcher | None, name: str, sink: list, **payload) -> None:
    if dispatcher is None:
        return
    sink.extend(
        f"event subscriber {err.subscriber} failed on {name}: {err.error}"
        for err in dispatcher.emit(name, **payload)
    )


# ---------------------------------------------------------------------------
# Adapter execution
# ---------------------------------------------------------------------------


def _probe_capability(adapter, ctx) -> AdapterCapability:
    try:
        return adapter.capability(ctx)
    except Exception as exc:  # noqa: BLE001 — a broken probe means "don't use"
        return AdapterCapability(id=getattr(adapter, "id", "?"), supported=False,
                                 reason=f"capability probe failed: {exc}")


def _drive_adapter(adapter, ctx) -> AdapterResult:
    aid = getattr(adapter, "id", "?")
    try:
        plan = adapter.plan(ctx.theme, ctx)
        adapter.render(ctx.theme, ctx.generation_dir, ctx)
        applied = adapter.apply(plan, ctx)
        verified = adapter.verify(plan, ctx)
    except Exception as exc:  # noqa: BLE001 — captured, never propagated
        return AdapterResult(
            adapter_id=aid,
            attempted=True,
            errors=(f"{type(exc).__name__}: {exc}",),
        )
    return AdapterResult(
        adapter_id=aid,
        attempted=True,
        applied=bool(getattr(applied, "applied", False)),
        verified=bool(getattr(verified, "verified", False)),
        supported=True,
        warnings=tuple(getattr(applied, "warnings", ()) or ())
        + tuple(getattr(verified, "warnings", ()) or ()),
        errors=tuple(getattr(applied, "errors", ()) or ())
        + tuple(getattr(verified, "errors", ()) or ()),
    )


def _rollback_adapters(
    registry: AdapterRegistry, ctx: ActivationContext
) -> tuple[list[AdapterResult], list[str]]:
    results: list[AdapterResult] = []
    errors: list[str] = []
    for adapter in registry.adapters:
        aid = getattr(adapter, "id", "?")
        try:
            result = adapter.rollback(ctx.previous_state, ctx)
        except Exception as exc:  # noqa: BLE001 — best-effort rollback
            errors.append(f"adapter {aid} rollback raised: {exc}")
            continue
        problems = tuple(getattr(result, "errors", ()) or ())
        results.append(result)
        errors.extend(f"adapter {aid} rollback: {p}" for p in problems)
    return results, errors


# ---------------------------------------------------------------------------
# Internal rollback (activation-time, before anything was persisted)
# ---------------------------------------------------------------------------


def _undo_activation(
    state_root: Path,
    prior_state: RuntimeState,
    registry: AdapterRegistry,
    dispatcher: EventDispatcher | None,
    warnings: list[str],
    errors: list[str],
    applied_manifest: Manifest | None = None,
) -> bool:
    """Best-effort return to *prior_state* after a failed promotion path.

    Pointers are reverted first, then files this attempt wrote but the
    prior state never owned are removed, previously-owned external
    files are restored, and finally adapters get their rollback turn.
    Returns True when nothing additional went wrong.
    """
    clean = True
    try:
        revert_to_state(state_root, prior_state)
    except StateError as exc:
        errors.append(f"pointer revert failed: {exc}")
        return False

    if applied_manifest is not None:
        prior_owned = prior_state.managed_map
        for entry in applied_manifest.files:
            target = Path(entry.target).expanduser()
            if str(target) in prior_owned:
                continue  # restored below from the prior generation
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f"cannot remove {target} during rollback: {exc}")
                clean = False

    prior_manifest = None
    if prior_state.current_generation is not None:
        try:
            prior_manifest = load_generation_manifest(state_root, prior_state.current_generation)
            errors.extend(
                _materialize_targets(
                    prior_manifest, generation_dir(state_root, prior_state.current_generation)
                )
            )
        except ThemeError as exc:
            errors.append(f"cannot restore previous generation files: {exc}")
            clean = False

    ctx = ActivationContext(
        state_root=state_root,
        generation_dir=(
            generation_dir(state_root, prior_state.current_generation)
            if prior_state.current_generation
            else state_root / "staging"
        ),
        manifest=prior_manifest or _empty_manifest(),
        theme=None,
        dry_run=False,
        previous_state=prior_state,
    )
    results, adapter_errors = _rollback_adapters(registry, ctx)
    errors.extend(adapter_errors)

    _emit(
        dispatcher,
        EVENT_PRE_ROLLBACK,
        warnings,
        from_theme=None,
        to_theme=prior_state.current_theme,
        from_generation=None,
        to_generation=prior_state.current_generation,
    )
    _emit(
        dispatcher,
        EVENT_POST_ROLLBACK,
        warnings,
        current_theme=prior_state.current_theme,
        generation=prior_state.current_generation,
    )
    return clean and not adapter_errors


def _empty_manifest() -> Manifest:
    return Manifest(
        theme_name="", theme_id="", theme_version=0, mode="dark",
        theme_source=Path("."), timestamp=utc_now_iso(), ownership="base", files=(),
    )


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def activate(
    theme_dir: str | Path,
    *,
    registry_path: str | Path,
    templates_root: str | Path,
    state_root: str | Path,
    user_theme_overlay_dir: str | Path | None = None,
    user_templates_dir: str | Path | None = None,
    adapters: AdapterRegistry | None = None,
    dispatcher: EventDispatcher | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> ActivationOutcome:
    """Run the full activation pipeline for the theme at *theme_dir*.

    Never raises for operational problems — failures come back as a
    FAILED/:data:`STATUS_ROLLED_BACK` outcome with populated ``errors``.
    Only programming/environment errors (bad arguments, unwritable
    state root) propagate.
    """
    registry = adapters if adapters is not None else AdapterRegistry()
    warnings: list[str] = []
    errors: list[str] = []

    root = Path(state_root).expanduser()
    prior_state = read_state(root)

    sandbox: Path | None = None
    effective_root = root
    if dry_run:
        ensure_layout(root)
        sandbox = Path(tempfile.mkdtemp(prefix=".dryrun-", dir=root))
        effective_root = sandbox

    try:
        return _activate_impl(
            theme_dir=theme_dir,
            registry_path=registry_path,
            templates_root=templates_root,
            state_root=effective_root,
            real_state_root=root,
            user_theme_overlay_dir=user_theme_overlay_dir,
            user_templates_dir=user_templates_dir,
            registry=registry,
            dispatcher=None if dry_run else dispatcher,
            force=force,
            dry_run=dry_run,
            prior_state=prior_state,
            warnings=warnings,
            errors=errors,
        )
    finally:
        if sandbox is not None:
            shutil.rmtree(sandbox, ignore_errors=True)


def _activate_impl(
    *,
    theme_dir,
    registry_path,
    templates_root,
    state_root: Path,
    real_state_root: Path,
    user_theme_overlay_dir,
    user_templates_dir,
    registry: AdapterRegistry,
    dispatcher: EventDispatcher | None,
    force: bool,
    dry_run: bool,
    prior_state: RuntimeState,
    warnings: list[str],
    errors: list[str],
) -> ActivationOutcome:
    common = {"dry_run": dry_run}

    # -- resolve / merge overlay / validate -------------------------------
    try:
        theme, _overlay_report = load_theme_with_overlay(theme_dir, user_theme_overlay_dir)
    except ThemeError as exc:
        return _outcome(STATUS_FAILED, errors=[f"cannot load theme: {exc}"], **common)

    issues = validate_theme(theme)
    rule_errors = [str(i) for i in issues if i.is_error]
    warnings.extend(str(i) for i in issues if not i.is_error)
    if rule_errors:
        errors.extend(rule_errors)
        errors.append("validation produced errors; refusing to stage")
        return _outcome(STATUS_FAILED, errors=errors, warnings=warnings, **common)

    _emit(
        dispatcher, EVENT_PRE_ACTIVATE, warnings,
        theme=theme.meta.name, theme_id=theme.meta.id,
        source=str(theme.path or theme_dir), force=force,
    )

    # -- render + stage ----------------------------------------------------
    try:
        staged = stage_theme(
            theme.path or theme_dir,
            registry_path=registry_path,
            templates_root=templates_root,
            user_theme_overlay_dir=user_theme_overlay_dir,
            user_templates_dir=user_templates_dir,
            state_root=state_root,
        )
    except ThemeError as exc:
        errors.append(f"staging failed: {exc}")
        return _outcome(STATUS_FAILED, errors=errors, warnings=warnings, **common)

    try:
        verify_staged_integrity(staged)
    except ActivationError as exc:
        errors.append(str(exc))
        return _outcome(
            STATUS_FAILED, phase=PHASE_CORE_STAGED, errors=errors, warnings=warnings, **common
        )

    manifest = _manifest_of(staged)

    # -- managed conflicts --------------------------------------------------
    conflicts = inspect_managed_conflicts(prior_state, manifest)
    if conflicts and not force and not dry_run:
        for c in conflicts:
            errors.append(
                f"conflict: {c.target} diverged from the engine's last-written "
                f"content ({c.managed_hash or 'untracked'}); "
                "use force to overwrite user modifications"
            )
        return _outcome(
            STATUS_FAILED,
            phase=PHASE_CORE_STAGED,
            conflicts=tuple(conflicts),
            errors=errors,
            warnings=warnings,
            **common,
        )
    for c in conflicts:
        warnings.append(f"forced overwrite of user-modified target {c.target}")

    # -- idempotent short-circuit -------------------------------------------
    current_gen = prior_state.current_generation
    if (
        not dry_run
        and prior_state.current_theme == theme.meta.id
        and current_gen is not None
        and generation_dir(real_state_root, current_gen).is_dir()
    ):
        try:
            current_manifest = load_generation_manifest(real_state_root, current_gen)
        except ThemeError:
            current_manifest = None
        if current_manifest is not None and (
            manifest_hash_map(current_manifest) == manifest_hash_map(manifest)
        ):
            return _finish_idempotent(
                real_state_root=real_state_root,
                prior_state=prior_state,
                manifest=manifest,
                registry=registry,
                dispatcher=dispatcher,
                theme=theme,
                warnings=warnings,
            )

    if dry_run:
        return _outcome(
            STATUS_DRY_RUN,
            phase=PHASE_CORE_STAGED,
            theme_id=theme.meta.id,
            theme_name=theme.meta.name,
            theme_source=theme.path,
            planned_targets=tuple(
                {
                    "target": str(Path(entry.target).expanduser()),
                    "name": entry.name,
                    "adapter": entry.adapter,
                }
                for entry in manifest.files
            ),
            conflicts=tuple(conflicts),
            capabilities=tuple(_probe_capability(a, _dry_ctx(state_root, manifest, theme,
                                                              prior_state))
                               for a in registry.adapters),
            warnings=warnings,
            errors=errors,
            **common,
        )

    # -- prepare + promote ---------------------------------------------------
    gen_id = new_generation_id()
    gen_dir = generation_dir(real_state_root, gen_id)
    try:
        real_state_root.joinpath("generations").mkdir(parents=True, exist_ok=True)
        os.replace(staged.staging_dir, gen_dir)
        filesystem.ensure_dir(staged.staging_dir)
    except OSError as exc:
        errors.append(f"cannot prepare generation {gen_id}: {exc}")
        return _outcome(
            STATUS_FAILED, phase=PHASE_CORE_STAGED, errors=errors, warnings=warnings, **common
        )

    try:
        promote_generation(real_state_root, gen_id)
    except StateError as exc:
        errors.append(f"promotion failed: {exc}")
        clean = _undo_activation(
            real_state_root, prior_state, registry, dispatcher, warnings, errors
        )
        return _outcome(
            STATUS_ROLLED_BACK if clean else STATUS_FAILED,
            phase=PHASE_CORE_STAGED,
            theme_id=theme.meta.id,
            theme_name=theme.meta.name,
            theme_source=theme.path,
            generation=gen_id,
            rollback_performed=clean,
            errors=errors,
            warnings=warnings,
            **common,
        )

    phase = PHASE_CORE_PROMOTED

    # -- materialize owned targets + core verification ------------------------
    errors.extend(_materialize_targets(manifest, gen_dir))
    errors.extend(_verify_targets(manifest))
    if errors:
        _undo_activation(
            real_state_root,
            prior_state,
            registry,
            dispatcher,
            warnings,
            errors,
            applied_manifest=manifest,
        )
        errors.append("core apply/verify failed; activation rolled back")
        return _outcome(
            STATUS_ROLLED_BACK,
            phase=phase,
            theme_id=theme.meta.id,
            theme_name=theme.meta.name,
            theme_source=theme.path,
            generation=gen_id,
            previous_generation=prior_state.current_generation,
            rollback_performed=True,
            conflicts=tuple(conflicts),
            errors=errors,
            warnings=warnings,
            **common,
        )

    _emit(dispatcher, EVENT_POST_CORE_ACTIVATE, warnings,
          theme_id=theme.meta.id, generation=gen_id, core_changed=True)

    # -- adapters --------------------------------------------------------------
    ctx = ActivationContext(
        state_root=real_state_root,
        generation_dir=gen_dir,
        manifest=manifest,
        theme=theme,
        dry_run=False,
        previous_state=prior_state,
    )
    capabilities: list[AdapterCapability] = []
    results: list[AdapterResult] = []
    degraded = False
    critical_failure: tuple[str, AdapterResult] | None = None

    for adapter in registry.adapters:
        aid = getattr(adapter, "id", "?")
        cap = _probe_capability(adapter, ctx)
        capabilities.append(cap)
        if not cap.supported:
            results.append(AdapterResult.skipped(aid, cap.reason))
            warnings.append(
                f"adapter {aid} unsupported on this system"
                f"{f' ({cap.reason})' if cap.reason else ''}; skipping"
            )
            continue
        result = _drive_adapter(adapter, ctx)
        results.append(result)
        if result.failed:
            if registry.is_critical(aid):
                critical_failure = (aid, result)
                break
            degraded = True

    if critical_failure is not None:
        aid, bad = critical_failure
        errors.append(
            f"critical adapter {aid} failed; rolling back activation "
            f"({'; '.join(bad.errors) or 'apply/verify reported failure'})"
        )
        clean = _undo_activation(
            real_state_root,
            prior_state,
            registry,
            dispatcher,
            warnings,
            errors,
            applied_manifest=manifest,
        )
        return _outcome(
            STATUS_ROLLED_BACK if clean else STATUS_FAILED,
            phase=PHASE_ADAPTERS_APPLIED,
            theme_id=theme.meta.id,
            theme_name=theme.meta.name,
            theme_source=theme.path,
            generation=gen_id,
            previous_generation=prior_state.current_generation,
            conflicts=tuple(conflicts),
            capabilities=tuple(capabilities),
            adapter_results=tuple(results),
            rollback_performed=True,
            errors=errors,
            warnings=warnings,
            **common,
        )

    phase = PHASE_ADAPTERS_APPLIED

    # -- persist -----------------------------------------------------------------
    previous_theme = prior_state.current_theme
    previous_generation = prior_state.current_generation
    adapters_summary = {}
    for cap, result in zip(capabilities, results):
        adapters_summary[result.adapter_id] = {
            "supported": cap.supported,
            "applied": result.applied,
            "verified": result.verified,
            "critical": registry.is_critical(result.adapter_id)
            if result.adapter_id in registry
            else False,
        }
    new_state = RuntimeState(
        current_theme=theme.meta.id,
        previous_theme=previous_theme,
        activated_at=utc_now_iso(),
        current_generation=gen_id,
        previous_generation=previous_generation,
        managed_targets=_merged_managed(prior_state, manifest),
        adapters=adapters_summary,
    )
    write_state(real_state_root, new_state)

    _emit(dispatcher, EVENT_POST_VERIFY, warnings,
          theme_id=theme.meta.id, generation=gen_id, ok=not degraded,
          errors=[e for r in results for e in r.errors])
    final_status = STATUS_DEGRADED if (degraded or errors) else STATUS_VERIFIED
    _emit(dispatcher, EVENT_POST_ACTIVATE, warnings,
          theme_id=theme.meta.id, status=final_status, generation=gen_id)

    return _outcome(
        final_status,
        # A degraded run stops short of full verification: report the
        # last completed lifecycle stage, not an optimistic one.
        phase=PHASE_VERIFIED if final_status == STATUS_VERIFIED else PHASE_ADAPTERS_APPLIED,
        theme_id=theme.meta.id,
        theme_name=theme.meta.name,
        theme_source=theme.path,
        generation=gen_id,
        previous_generation=previous_generation,
        core_changed=True,
        conflicts=tuple(conflicts),
        capabilities=tuple(capabilities),
        adapter_results=tuple(results),
        errors=errors,
        warnings=warnings,
        **common,
    )


def _finish_idempotent(
    *,
    real_state_root: Path,
    prior_state: RuntimeState,
    manifest: Manifest,
    registry: AdapterRegistry,
    dispatcher: EventDispatcher | None,
    theme,
    warnings: list[str],
) -> ActivationOutcome:
    """Same theme, identical content: keep the current generation."""
    gen_id = prior_state.current_generation
    gen_dir = generation_dir(real_state_root, gen_id)
    warnings.append(
        f"theme {theme.meta.id!r} already active with identical content; "
        f"keeping generation {gen_id}"
    )
    _emit(dispatcher, EVENT_POST_CORE_ACTIVATE, warnings,
          theme_id=theme.meta.id, generation=gen_id, core_changed=False)

    ctx = ActivationContext(
        state_root=real_state_root,
        generation_dir=gen_dir,
        manifest=manifest,
        theme=theme,
        dry_run=False,
        previous_state=prior_state,
    )
    capabilities, results, degraded = [], [], False
    for adapter in registry.adapters:
        aid = getattr(adapter, "id", "?")
        cap = _probe_capability(adapter, ctx)
        capabilities.append(cap)
        if not cap.supported:
            results.append(AdapterResult.skipped(aid, cap.reason))
            continue
        result = _drive_adapter(adapter, ctx)
        results.append(result)
        if result.failed:
            # Content did not change; a failing adapter is a health
            # signal, not a reason to churn generations.
            degraded = True

    adapters_summary = {}
    for cap, result in zip(capabilities, results):
        adapters_summary[result.adapter_id] = {
            "supported": cap.supported,
            "applied": result.applied,
            "verified": result.verified,
            "critical": registry.is_critical(result.adapter_id)
            if result.adapter_id in registry
            else False,
        }
    write_state(
        real_state_root,
        RuntimeState(
            current_theme=prior_state.current_theme,
            previous_theme=prior_state.previous_theme,
            activated_at=prior_state.activated_at,
            current_generation=prior_state.current_generation,
            previous_generation=prior_state.previous_generation,
            managed_targets=prior_state.managed_targets,
            adapters=adapters_summary,
        ),
    )

    _emit(dispatcher, EVENT_POST_VERIFY, warnings,
          theme_id=theme.meta.id, generation=gen_id, ok=not degraded, errors=[])
    status = STATUS_DEGRADED if degraded else STATUS_VERIFIED
    _emit(dispatcher, EVENT_POST_ACTIVATE, warnings,
          theme_id=theme.meta.id, status=status, generation=gen_id)
    return _outcome(
        status,
        phase=PHASE_VERIFIED,
        theme_id=theme.meta.id,
        theme_name=theme.meta.name,
        theme_source=theme.path,
        generation=gen_id,
        previous_generation=prior_state.previous_generation,
        conflicts=(),
        capabilities=tuple(capabilities),
        adapter_results=tuple(results),
        warnings=warnings,
        dry_run=False,
    )


def _dry_ctx(state_root: Path, manifest: Manifest, theme, prior_state: RuntimeState):
    return ActivationContext(
        state_root=state_root,
        generation_dir=state_root / "staging",
        manifest=manifest,
        theme=theme,
        dry_run=True,
        previous_state=prior_state,
    )


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback(
    *,
    state_root: str | Path,
    adapters: AdapterRegistry | None = None,
    dispatcher: EventDispatcher | None = None,
) -> ActivationOutcome:
    """Switch back to the recorded previous generation.

    Raises :class:`RollbackError` when there is nothing to roll back to
    or the recorded generation vanished (missing directory/manifest) —
    the request can never succeed, so callers must hear it loudly.
    Mid-operation problems degrade the outcome instead.
    """
    root = ensure_layout(Path(state_root).expanduser())
    registry = adapters if adapters is not None else AdapterRegistry()
    warnings: list[str] = []
    errors: list[str] = []

    state = read_state(root)
    prev_id = state.previous_generation
    if prev_id is None:
        raise RollbackError(
            "no previous generation recorded in state.json; nothing to roll back to"
        )
    prev_dir = generation_dir(root, prev_id)
    if not prev_dir.is_dir():
        raise RollbackError(
            f"previous generation {prev_id!r} is gone from {prev_dir} "
            "(stale state; cannot roll back)"
        )
    try:
        prev_manifest = load_generation_manifest(root, prev_id)
    except ThemeError as exc:
        raise RollbackError(
            f"previous generation {prev_id!r} has no usable manifest ({exc}); "
            "refusing to roll back"
        ) from exc

    current_id = state.current_generation
    _emit(
        dispatcher, EVENT_PRE_ROLLBACK, warnings,
        from_theme=state.current_theme, to_theme=state.previous_theme,
        from_generation=current_id, to_generation=prev_id,
    )

    # 1. pointers: current ← previous, previous ← demoted current
    try:
        if current_id is not None:
            switch_link(root, PREVIOUS_LINK, current_id)
        else:
            (root / PREVIOUS_LINK).unlink(missing_ok=True)
        switch_link(root, CURRENT_LINK, prev_id)
    except StateError as exc:
        errors.append(f"pointer switch failed: {exc}")
        return _outcome(
            STATUS_FAILED,
            phase=PHASE_CORE_PROMOTED,
            theme_id=state.previous_theme,
            generation=current_id,
            errors=errors,
            warnings=warnings,
            dry_run=False,
        )

    # 2. restore only Omni-owned external files from the previous manifest
    errors.extend(_materialize_targets(prev_manifest, prev_dir))

    # 3. adapters roll back where they can
    ctx = ActivationContext(
        state_root=root,
        generation_dir=prev_dir,
        manifest=prev_manifest,
        theme=None,
        dry_run=False,
        previous_state=state,
    )
    adapter_results, adapter_errors = _rollback_adapters(registry, ctx)
    errors.extend(adapter_errors)

    # 4. metadata
    new_state = RuntimeState(
        current_theme=state.previous_theme,
        previous_theme=state.current_theme,
        activated_at=utc_now_iso(),
        current_generation=prev_id,
        previous_generation=current_id,
        managed_targets=_merged_managed(state, prev_manifest),
        adapters=state.adapters,
    )
    write_state(root, new_state)

    _emit(
        dispatcher, EVENT_POST_ROLLBACK, warnings,
        current_theme=new_state.current_theme, generation=prev_id,
    )

    return _outcome(
        STATUS_ROLLED_BACK,
        phase=PHASE_CORE_PROMOTED,
        theme_id=new_state.current_theme,
        theme_name=prev_manifest.theme_name or new_state.current_theme,
        generation=prev_id,
        previous_generation=current_id,
        core_changed=True,
        rollback_performed=True,
        adapter_results=tuple(adapter_results),
        errors=errors,
        warnings=warnings,
        dry_run=False,
    )
