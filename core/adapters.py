"""Desktop-agnostic adapter contract for omni-theme-cachy.

An adapter is the unit that knows how one desktop surface consumes a
theme (a color scheme file plus a Plasma reload, a terminal config, an
editor theme, …). The core engine never imports concrete adapters; it
drives whatever is registered here through this protocol.

Contract semantics
------------------

* **Unsupported is not failure.** ``capability()`` decides participation
  per machine (KDE present? VS Code installed?). An unsupported adapter
  is *skipped and reported*, and overall activation still succeeds.
* **Criticality is explicit metadata.** A supported adapter whose
  ``apply``/``verify`` fails marks the activation DEGRADED — unless the
  registry recorded it as *critical*, in which case the engine rolls
  back deterministically. Criticality is data supplied at registration
  time (or a ``critical`` attribute), never an exception path.
* **Results are values.** Every phase reports an :class:`AdapterResult`;
  exceptions are captured into results by the engine so one broken
  adapter cannot take down the run.

Phases an adapter may participate in, in order::

    capability → plan → render → apply → verify      (activation)
    rollback                                          (rollback)

``capability`` must be a pure query. ``render`` receives the promoted
generation directory as a read-only artifact tree; adapters write their
own external outputs during ``apply``, not before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.errors import AdapterError
from core.events import LIFECYCLE_EVENTS, EventDispatcher

__all__ = [
    "AdapterCapability",
    "AdapterResult",
    "ThemeAdapter",
    "AdapterRegistry",
]


@dataclass(frozen=True)
class AdapterCapability:
    """What an adapter declares about itself on this machine."""

    id: str
    supported: bool
    #: Why not, when ``supported`` is False ("plasma-notify not found").
    reason: str | None = None
    #: Detected version of the target application, when known.
    version: str | None = None


@dataclass(frozen=True)
class AdapterResult:
    """Outcome of driving one adapter through a phase.

    The engine merges ``apply``/``verify`` outcomes into one result per
    adapter per activation; ``rolled_back`` is set on rollback runs.
    """

    adapter_id: str
    attempted: bool = True
    applied: bool = False
    verified: bool = False
    rolled_back: bool = False
    supported: bool = True
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return bool(self.errors) or (self.attempted and not (self.applied and self.verified))

    @staticmethod
    def skipped(adapter_id: str, reason: str | None = None) -> "AdapterResult":
        """Result for an adapter that was not attempted (unsupported)."""
        warnings = (reason,) if reason else ()
        return AdapterResult(
            adapter_id=adapter_id,
            attempted=False,
            supported=False,
            warnings=warnings,
        )

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "attempted": self.attempted,
            "applied": self.applied,
            "verified": self.verified,
            "rolled_back": self.rolled_back,
            "supported": self.supported,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@runtime_checkable
class ThemeAdapter(Protocol):
    """Structural interface every adapter satisfies.

    ``id`` must be unique within a registry. ``critical`` is optional
    metadata (default False) consulted when the registry records no
    explicit criticality at registration time.
    """

    id: str

    def capability(self, context) -> AdapterCapability: ...

    def plan(self, resolved_theme, context): ...

    def render(self, resolved_theme, staging, context): ...

    def apply(self, plan, context) -> AdapterResult: ...

    def verify(self, plan, context) -> AdapterResult: ...

    def rollback(self, previous_state, context) -> AdapterResult: ...


@dataclass(frozen=True)
class _Registration:
    adapter: ThemeAdapter
    critical: bool


class AdapterRegistry:
    """Ordered collection of adapters plus their criticality metadata.

    Registration order is execution order. The registry knows how to
    forward lifecycle events to adapters that implement an optional
    ``on_event(event)`` method, so the activation engine stays free of
    hard-coded adapter wiring:

    ::

        registry.register(KdeAdapter(), critical=True)
        registry.attach(engine.dispatcher)
    """

    def __init__(self) -> None:
        self._order: list[str] = []
        self._by_id: dict[str, _Registration] = {}
        self._attach_token = 0

    # -- population ----------------------------------------------------

    def register(self, adapter: ThemeAdapter, *, critical: bool | None = None) -> None:
        """Add *adapter*; duplicate ids raise :class:`core.errors.AdapterError`.

        ``critical=None`` defers to the adapter's own ``critical``
        attribute (defaulting to False); an explicit value wins.
        """
        adapter_id = getattr(adapter, "id", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise AdapterError(f"adapter {adapter!r} has no non-empty string 'id'")
        if adapter_id in self._by_id:
            raise AdapterError(f"adapter id already registered: {adapter_id!r}")
        effective = (
            bool(getattr(adapter, "critical", False)) if critical is None else bool(critical)
        )
        self._order.append(adapter_id)
        self._by_id[adapter_id] = _Registration(adapter=adapter, critical=effective)

    # -- queries ---------------------------------------------------------

    @property
    def adapters(self) -> tuple[ThemeAdapter, ...]:
        return tuple(self._by_id[aid].adapter for aid in self._order)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._order)

    def get(self, adapter_id: str) -> ThemeAdapter:
        try:
            return self._by_id[adapter_id].adapter
        except KeyError:
            raise AdapterError(f"no adapter registered with id {adapter_id!r}") from None

    def __contains__(self, adapter_id: str) -> bool:
        return adapter_id in self._by_id

    def __len__(self) -> int:
        return len(self._order)

    def is_critical(self, adapter_id: str) -> bool:
        try:
            return self._by_id[adapter_id].critical
        except KeyError:
            raise AdapterError(f"no adapter registered with id {adapter_id!r}") from None

    # -- event plumbing ---------------------------------------------------

    def attach(self, dispatcher: EventDispatcher) -> None:
        """Subscribe a fan-out handler for every lifecycle event.

        Adapters implementing ``on_event(event)`` receive each event;
        one adapter raising does not stop the others — all failures are
        aggregated into a single error the dispatcher can report.
        """
        self._attach_token += 1
        owner = f"adapter-registry:{self._attach_token}"

        def _forward(event) -> None:
            failures: list[str] = []
            for adapter in self.adapters:
                handler = getattr(adapter, "on_event", None)
                if not callable(handler):
                    continue
                try:
                    handler(event)
                except Exception as exc:  # noqa: BLE001 — aggregate, don't abort
                    failures.append(f"{adapter.id}: {exc}")
            if failures:
                raise RuntimeError("; ".join(failures))

        for name in LIFECYCLE_EVENTS:
            dispatcher.subscribe(name, _forward, owner=owner)

    def detach(self, dispatcher: EventDispatcher) -> None:
        """Remove everything :meth:`attach` subscribed."""
        prefix = "adapter-registry:"
        owners = {
            owner
            for name in LIFECYCLE_EVENTS
            for owner, _ in dispatcher._subscribers.get(name, [])
            if owner.startswith(prefix)
        }
        for owner in sorted(owners):
            dispatcher.unsubscribe_owner(owner)
