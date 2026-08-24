"""Engine facade for omni-theme-cachy.

:class:`ThemeEngine` is the one object a CLI or script talks to; it
wires theme discovery, the session-03 staging pipeline, the session-04
runtime state, adapter registry and event dispatcher together::

    engine = ThemeEngine()
    outcome = engine.apply("tokyo-night")            # full activation
    outcome = engine.apply("tokyo-night", dry_run=True)   # plan only
    engine.rollback()                                 # explicit revert
    engine.status()                                   # inspect runtime

Nothing here knows about KDE, GTK, terminals or any other desktop
surface — adapters register themselves through :class:`AdapterRegistry`
and observe lifecycle events through :class:`EventDispatcher`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core import filesystem
from core.adapters import AdapterRegistry
from core.activation import ActivationOutcome, activate, rollback
from core.errors import ThemeError
from core.events import EventDispatcher
from core.state import (
    CURRENT_LINK,
    PREVIOUS_LINK,
    RuntimeState,
    generation_dir,
    link_target,
    read_state,
)
from core.theme_loader import find_theme, load_theme

__all__ = ["RuntimeStatus", "ThemeEngine"]

DEFAULT_THEMES_ROOT = Path("themes")
DEFAULT_TEMPLATES_ROOT = Path("templates")


@dataclass(frozen=True)
class RuntimeStatus:
    """Point-in-time view of the runtime state (for humans and CLIs)."""

    state_exists: bool
    current_theme: str | None
    previous_theme: str | None
    current_generation: str | None
    previous_generation: str | None
    activated_at: str | None
    managed_targets: int
    consistent: bool
    details: tuple[str, ...] = ()
    adapters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "state_exists": self.state_exists,
            "current_theme": self.current_theme,
            "previous_theme": self.previous_theme,
            "current_generation": self.current_generation,
            "previous_generation": self.previous_generation,
            "activated_at": self.activated_at,
            "managed_targets": self.managed_targets,
            "consistent": self.consistent,
            "details": list(self.details),
            "adapters": {k: dict(v) for k, v in sorted(self.adapters.items())},
        }


class ThemeEngine:
    """High-level API: apply themes atomically, roll back explicitly."""

    def __init__(
        self,
        *,
        themes_root: str | Path = DEFAULT_THEMES_ROOT,
        templates_root: str | Path = DEFAULT_TEMPLATES_ROOT,
        registry_path: str | Path | None = None,
        user_overlays_root: str | Path | None = None,
        user_templates_dir: str | Path | None = None,
        state_root: str | Path | None = None,
        adapters: AdapterRegistry | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self.themes_root = Path(themes_root)
        self.templates_root = Path(templates_root)
        self.registry_path = (
            Path(registry_path) if registry_path else self.templates_root / "targets.toml"
        )
        self.user_overlays_root = (
            Path(user_overlays_root) if user_overlays_root else filesystem.omni_config_dir() / "themes"
        )
        self.user_templates_dir = (
            Path(user_templates_dir) if user_templates_dir else filesystem.omni_config_dir() / "templates"
        )
        self.state_root = (
            Path(state_root) if state_root else filesystem.omni_state_dir()
        )
        self.registry = adapters if adapters is not None else AdapterRegistry()
        self.dispatcher = dispatcher if dispatcher is not None else EventDispatcher()
        self.registry.attach(self.dispatcher)

    # -- apply / rollback --------------------------------------------------

    def apply(
        self,
        reference: str | Path,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> ActivationOutcome:
        """Resolve *reference* (id, name or path) and activate it.

        Operational failures come back inside the outcome (status
        FAILED/ROLLED_BACK); only an unresolvable *reference* raises.
        """
        theme_dir = find_theme(self.themes_root, reference)
        return activate(
            theme_dir,
            registry_path=self.registry_path,
            templates_root=self.templates_root,
            state_root=self.state_root,
            user_theme_overlay_dir=self._overlay_for(theme_dir),
            user_templates_dir=self.user_templates_dir,
            adapters=self.registry,
            dispatcher=self.dispatcher,
            force=force,
            dry_run=dry_run,
        )

    #: Alias matching the historical ``apply_theme`` naming.
    def apply_theme(self, reference: str | Path, **kwargs) -> ActivationOutcome:
        return self.apply(reference, **kwargs)

    def rollback(self) -> ActivationOutcome:
        """Roll back to the recorded previous generation."""
        return rollback(
            state_root=self.state_root,
            adapters=self.registry,
            dispatcher=self.dispatcher,
        )

    # -- introspection ------------------------------------------------------

    def read_state(self) -> RuntimeState:
        """Freshly-read runtime state (empty when never activated)."""
        return read_state(self.state_root)

    def current_theme(self) -> str | None:
        """Theme id recorded as current, or None."""
        return self.read_state().current_theme

    def previous_theme(self) -> str | None:
        """Theme id recorded as rollback target, or None."""
        return self.read_state().previous_theme

    def status(self) -> RuntimeStatus:
        """State metadata cross-checked against the actual pointers."""
        st = self.read_state()
        exists = (self.state_root / "state.json").is_file()
        details: list[str] = []
        consistent = True

        if exists:
            for label, gen_id in (
                (CURRENT_LINK, st.current_generation),
                (PREVIOUS_LINK, st.previous_generation),
            ):
                linked = link_target(self.state_root, label)
                if gen_id is None and linked is None:
                    continue
                if gen_id is not None and linked == gen_id:
                    if generation_dir(self.state_root, gen_id).is_dir():
                        continue
                    details.append(f"{label}: generation directory missing: {gen_id}")
                    consistent = False
                    continue
                details.append(
                    f"{label}: state records {gen_id!r} but symlink points at {linked!r}"
                )
                consistent = False

        return RuntimeStatus(
            state_exists=exists,
            current_theme=st.current_theme,
            previous_theme=st.previous_theme,
            current_generation=st.current_generation,
            previous_generation=st.previous_generation,
            activated_at=st.activated_at,
            managed_targets=len(st.managed_targets),
            consistent=consistent,
            details=tuple(details),
            adapters=dict(st.adapters),
        )

    # -- helpers --------------------------------------------------------------

    def _overlay_for(self, theme_dir: Path) -> Path | None:
        """User overlay dir for *theme_dir* (theme.id wins, then dirname)."""
        candidates: list[Path] = []
        try:
            meta = load_theme(theme_dir).meta
            candidates.append(self.user_overlays_root / meta.id)
        except ThemeError:
            pass
        candidates.append(self.user_overlays_root / theme_dir.name)
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return candidates[0]
