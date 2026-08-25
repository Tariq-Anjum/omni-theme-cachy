"""GTK adapter: KDE-sync first, explicit direct fallback, honest reporting.

Strategy ladder
---------------
1. **kde-sync** (preferred, automatic): when KDE's gtk integration is
   present, applying a Color Scheme already propagates colors into
   ``colors.css``/``gtk.css`` via kde-gtk-config. This adapter writes
   *nothing* in this mode — it verifies the propagation instead, so two
   owners never fight over the same files.
2. **direct** (explicit opt-in only): generate an owned, marker-wrapped
   block inside ``gtk-{3,4}.0/gtk.css`` (see :mod:`adapters.gtk.direct`).
3. **observe** (default when no integration exists): report capability
   and explain why nothing is written. Unsupported must not masquerade
   as failure, and absence of a strategy must not silently write files.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from core.adapters import AdapterCapability, AdapterResult
from core.errors import AdapterError
from core.filesystem import sha256_file

from adapters.gtk import direct as gtk_direct
from adapters.gtk import sync as gtk_sync
from adapters.gtk.detection import (
    TOOL_KCMSHELL6,
    GtkEnvironment,
    detect_gtk,
)

__all__ = ["GtkAdapter", "GtkPlan", "MODE_KDE_SYNC", "MODE_DIRECT", "MODE_OBSERVE"]

MODE_KDE_SYNC = "kde-sync"
MODE_DIRECT = "direct"
MODE_OBSERVE = "observe"

#: CSS custom properties written in direct mode (name ← palette role).
DIRECT_COLORS: tuple[tuple[str, str], ...] = (
    ("omni-bg", "background"),
    ("omni-fg", "foreground"),
    ("omni-accent", "accent"),
    ("omni-selection", "selection"),
    ("omni-error", "error"),
    ("omni-success", "success"),
    ("omni-warning", "warning"),
)


@dataclass(frozen=True)
class GtkPlan:
    """Read-only intent for one activation."""

    mode: str
    environment: GtkEnvironment
    #: Direct-mode targets and their plans (empty in other modes).
    direct_plans: tuple[gtk_direct.DirectWritePlan, ...] = ()
    warnings: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "direct_targets": [str(p.target) for p in self.direct_plans],
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


class GtkAdapter:
    """Reports and (only where safe) drives GTK theming."""

    id = "gtk"

    def __init__(
        self,
        *,
        allow_direct: bool = False,
        direct_force: bool = False,
        env=None,
        which=None,
        config_home=None,
    ) -> None:
        self._allow_direct = allow_direct
        self._direct_force = direct_force
        self._kwargs: dict = {}
        if env is not None:
            self._kwargs["env"] = env
        if which is not None:
            self._kwargs["which"] = which
        if config_home is not None:
            self._kwargs["config_home"] = config_home
        self._detected: GtkEnvironment | None = None

    def environment(self) -> GtkEnvironment:
        if self._detected is None:
            self._detected = detect_gtk(**self._kwargs)
        return self._detected

    # -- contract phases -------------------------------------------------------

    def capability(self, context) -> AdapterCapability:
        env = self.environment()
        if not env.has_gtk():
            return AdapterCapability(
                id=self.id,
                supported=False,
                reason="no GTK configuration found "
                f"(no {', '.join(('gtk-3.0', 'gtk-4.0'))} under config home)",
            )
        return AdapterCapability(id=self.id, supported=True)

    def plan(self, resolved_theme, context) -> GtkPlan:
        env = self.environment()
        warnings: list[str] = []
        details: dict = {}

        if env.kde_gtk_integration:
            mode = MODE_KDE_SYNC
            details["signal"] = (
                f"{TOOL_KCMSHELL6} present" if env.has(TOOL_KCMSHELL6)
                else "colorreload-gtk-module active"
            )
            details["theme_name"] = env.gtk_theme
            kg_text, css_text = gtk_sync.environment_sync_inputs(env)
            if css_text is None:
                warnings.append(
                    "kde-gtk-config integration detected but no gtk-3.0/colors.css "
                    "yet; open System Settings → Colors & Themes once or apply any "
                    "color scheme to trigger synchronization"
                )
            else:
                problems = gtk_sync.verify_sync(kg_text or "", css_text)
                details["sync_problems"] = problems
        elif self._allow_direct:
            mode = MODE_DIRECT
        else:
            mode = MODE_OBSERVE
            warnings.append(
                "no KDE GTK integration detected; GTK apps will keep their "
                "current theme (enable direct generation explicitly with "
                "GtkAdapter(allow_direct=True) after testing)"
            )

        direct_plans: tuple[gtk_direct.DirectWritePlan, ...] = ()
        if mode == MODE_DIRECT:
            colors = {
                name: (resolved_theme.palette.get(role) or "").lower()
                for name, role in DIRECT_COLORS
                if resolved_theme.palette.get(role)
            }
            plans = []
            # Only gtk-3.0/gtk.css is owned in direct mode: libadwaita
            # (GTK4) intentionally ignores external theme engines, and
            # pretending otherwise would promise something we cannot
            # deliver.
            target = env.dir("gtk-3.0") / "gtk.css"
            # Ownership conflicts raise here on purpose: mixing generated
            # CSS into unknown user content is refused, not warned about.
            # Only an explicit force (mirroring the engine's conflict
            # policy) replaces foreign content wholesale.
            plans.append(
                gtk_direct.plan_direct_write(
                    target,
                    colors,
                    generation=_generation_of(context),
                    theme_id=resolved_theme.meta.id,
                    force=self._direct_force,
                )
            )
            direct_plans = tuple(plans)
            if env.has_gtk("gtk-4.0"):
                warnings.append(
                    "direct generation targets gtk-3.0 only; libadwaita/GTK4 "
                    "apps ignore user theme CSS by design and stay unstyled"
                )

        return GtkPlan(
            mode=mode,
            environment=env,
            direct_plans=direct_plans,
            warnings=tuple(warnings),
            details=details,
        )

    def render(self, resolved_theme, staging, context) -> None:
        """No staged artifacts; output is computed during plan/apply."""

    def apply(self, plan: GtkPlan, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = list(plan.warnings)

        if plan.mode == MODE_KDE_SYNC:
            # Delegation *is* the mechanism: KDE writes, we verify later.
            return self._result(applied=True, verified=False, warnings=warnings)

        if plan.mode == MODE_OBSERVE:
            return self._result(applied=True, warnings=warnings)

        journal = gtk_direct.GtkJournal.load(
            gtk_direct.gtk_journal_path(context.state_root)
        )
        changed_any = False
        for dplan in plan.direct_plans:
            if not dplan.writable:
                continue
            try:
                changed = gtk_direct.apply_direct_write(
                    dplan,
                    journal,
                    backup_dir=context.state_root / "adapters" / "gtk-backups",
                )
                changed_any = changed or changed_any
                if dplan.action == "replace-block":
                    warnings.append(
                        f"replaced omni-theme managed block in {dplan.target} "
                        f"(was generation {dplan.existing_generation})"
                    )
            except (AdapterError, OSError) as exc:
                errors.append(f"direct gtk write failed for {dplan.target}: {exc}")
        if changed_any:
            journal.save()

        return self._result(applied=not errors, warnings=warnings, errors=errors)

    def verify(self, plan: GtkPlan, context) -> AdapterResult:
        errors: list[str] = []

        if plan.mode == MODE_KDE_SYNC:
            kg_text, css_text = gtk_sync.environment_sync_inputs(plan.environment)
            if css_text is None:
                # Absence of the file is a warning-grade gap (first boot,
                # module not yet triggered), not proof of broken sync.
                return self._result(
                    applied=True,
                    verified=True,
                    warnings=(
                        "cannot verify kde-gtk sync: no colors.css present",
                    ),
                )
            problems = gtk_sync.verify_sync(kg_text or "", css_text)
            hard = [p for p in problems if "missing" not in p]
            soft = [p for p in problems if "missing" in p]
            errors.extend(hard)
            return self._result(
                applied=True, verified=not errors, warnings=tuple(soft), errors=errors
            )

        if plan.mode == MODE_DIRECT:
            for dplan in plan.direct_plans:
                if not dplan.target.is_file():
                    errors.append(f"managed file missing after apply: {dplan.target}")
                    continue
                actual_hash = sha256_file(dplan.target)
                expected = _text_hash(dplan.new_text)
                if actual_hash != expected:
                    errors.append(
                        f"{dplan.target} does not match planned content "
                        "(modified after write?)"
                    )
            return self._result(applied=True, verified=not errors)

        return self._result(applied=True, verified=True)

    def rollback(self, previous_state, context) -> AdapterResult:
        errors: list[str] = []
        warnings: list[str] = []
        journal = gtk_direct.GtkJournal.load(
            gtk_direct.gtk_journal_path(context.state_root)
        )

        if not journal.files:
            # kde-sync mode owns nothing; observe mode wrote nothing.
            return AdapterResult(
                adapter_id=self.id,
                rolled_back=True,
                warnings=("gtk adapter owns no files to revert",),
            )

        for key in sorted(journal.files):
            rolled, warns = gtk_direct.rollback_direct_write(Path(key), journal)
            warnings.extend(warns)
            if not rolled:
                errors.extend(warns)
        journal.save()
        return AdapterResult(
            adapter_id=self.id,
            rolled_back=not errors,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _result(*, applied=False, verified=False, warnings=(), errors=()) -> AdapterResult:
        return AdapterResult(
            adapter_id="gtk",
            attempted=True,
            applied=applied,
            verified=verified,
            supported=True,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )


def _generation_of(context) -> str:
    """Stable provenance token for ownership markers within an activation."""
    manifest = getattr(context, "manifest", None)
    if manifest is None:
        return "unknown"
    timestamp = getattr(manifest, "timestamp", "") or ""
    theme_id = getattr(manifest, "theme_id", "") or ""
    return f"{theme_id}@{timestamp}" if theme_id and timestamp else (timestamp or "unknown")


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
