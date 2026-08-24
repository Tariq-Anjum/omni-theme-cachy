"""Activation event lifecycle for omni-theme-cachy.

The engine emits a small, fixed set of lifecycle events while it works;
adapters and other observers subscribe through an
:class:`EventDispatcher` instead of being hard-coded into activation.

Lifecycle (successful apply)::

    pre_activate → post_core_activate → post_verify → post_activate

Rollback::

    pre_rollback → post_rollback

``pre_activate``/``post_activate``/``post_rollback`` are the original
three-event contract kept for compatibility; ``post_core_activate`` and
``post_verify`` are finer-grained hooks added because "core promoted"
and "everything verified" are genuinely different moments (a critical
adapter failure sits between them).

Delivery is synchronous and best-effort: a raising subscriber can never
abort an activation — :meth:`EventDispatcher.emit` captures the error
and reports it to the caller, which folds it into outcome warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "EVENT_PRE_ACTIVATE",
    "EVENT_POST_CORE_ACTIVATE",
    "EVENT_POST_ACTIVATE",
    "EVENT_POST_VERIFY",
    "EVENT_PRE_ROLLBACK",
    "EVENT_POST_ROLLBACK",
    "LIFECYCLE_EVENTS",
    "Event",
    "SubscriberError",
    "EventDispatcher",
]

EVENT_PRE_ACTIVATE = "pre_activate"
EVENT_POST_CORE_ACTIVATE = "post_core_activate"
EVENT_POST_ACTIVATE = "post_activate"
EVENT_POST_VERIFY = "post_verify"
EVENT_PRE_ROLLBACK = "pre_rollback"
EVENT_POST_ROLLBACK = "post_rollback"

#: Every lifecycle event name, in pipeline order.
LIFECYCLE_EVENTS: tuple[str, ...] = (
    EVENT_PRE_ACTIVATE,
    EVENT_POST_CORE_ACTIVATE,
    EVENT_POST_VERIFY,
    EVENT_POST_ACTIVATE,
    EVENT_PRE_ROLLBACK,
    EVENT_POST_ROLLBACK,
)

EventCallback = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """One emitted lifecycle event.

    *payload* is copied on construction so later mutation of the
    caller's dict cannot retroactively change what subscribers saw.
    """

    name: str
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))

    def get(self, key: str, default=None):
        return self.payload.get(key, default)

    def __str__(self) -> str:
        return f"{self.name}: {self.payload}"


@dataclass(frozen=True)
class SubscriberError:
    """A subscriber raised while handling an event."""

    subscriber: str
    error: str


class EventDispatcher:
    """Minimal synchronous pub/sub keyed by event name.

    Subscription order is delivery order. Subscribers are registered as
    ``(owner, callback)`` pairs so component-level cleanup (e.g. an
    adapter registry detaching itself) can remove exactly what it added.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[str, EventCallback]]] = {}

    def subscribe(self, event_name: str, callback: EventCallback, *, owner: str = "") -> None:
        """Register *callback* for *event_name*."""
        if not callable(callback):
            raise TypeError(f"event callback for {event_name!r} must be callable")
        self._subscribers.setdefault(event_name, []).append((owner, callback))

    def unsubscribe(self, event_name: str, callback: EventCallback) -> bool:
        """Remove one registration; True when something was removed."""
        entries = self._subscribers.get(event_name)
        if not entries:
            return False
        remaining = [(o, cb) for o, cb in entries if cb is not callback]
        if len(remaining) == len(entries):
            return False
        if remaining:
            self._subscribers[event_name] = remaining
        else:
            del self._subscribers[event_name]
        return True

    def unsubscribe_owner(self, owner: str) -> int:
        """Remove every registration tagged with *owner*; returns count."""
        removed = 0
        for name in list(self._subscribers):
            entries = self._subscribers[name]
            remaining = [(o, cb) for o, cb in entries if o != owner]
            removed += len(entries) - len(remaining)
            if remaining:
                self._subscribers[name] = remaining
            else:
                del self._subscribers[name]
        return removed

    def emit(self, event_name: str, **payload) -> list[SubscriberError]:
        """Deliver an :class:`Event` to all subscribers of *event_name*.

        Returns one :class:`SubscriberError` per raising subscriber; a
        broken subscriber never prevents later subscribers from running
        and never raises out of :meth:`emit`.
        """
        event = Event(name=event_name, payload=payload)
        errors: list[SubscriberError] = []
        for owner, callback in list(self._subscribers.get(event_name, [])):
            label = owner or getattr(callback, "__name__", "<callback>")
            try:
                callback(event)
            except Exception as exc:  # noqa: BLE001 — isolation is the point
                errors.append(SubscriberError(subscriber=label, error=f"{exc}"))
        return errors

    def subscriber_count(self, event_name: str) -> int:
        return len(self._subscribers.get(event_name, []))
