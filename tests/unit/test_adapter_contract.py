"""Unit tests for the adapter contract: value shapes and AdapterRegistry."""

from __future__ import annotations

import dataclasses

import pytest

from core.adapters import (
    AdapterCapability,
    AdapterRegistry,
    AdapterResult,
    ThemeAdapter,
)
from core.errors import AdapterError
from core.events import EVENT_POST_ACTIVATE, Event, EventDispatcher


class RecordingAdapter:
    """Minimal contract-conforming adapter used across session-04 tests."""

    def __init__(
        self,
        id: str = "stub",
        *,
        supported: bool = True,
        reason: str | None = None,
        version: str | None = None,
        critical: bool = False,
        fail_on_event: bool = False,
    ) -> None:
        self.id = id
        self.critical = critical
        self._capability = AdapterCapability(id=id, supported=supported, reason=reason,
                                             version=version)
        self.calls: list[tuple] = []
        self.events: list[Event] = []
        self.fail_on_event = fail_on_event

    def capability(self, context) -> AdapterCapability:
        self.calls.append(("capability",))
        return self._capability

    def plan(self, resolved_theme, context):
        self.calls.append(("plan",))
        return {"theme": getattr(resolved_theme, "meta", None)}

    def render(self, resolved_theme, staging, context):
        self.calls.append(("render", str(staging)))

    def apply(self, plan, context) -> AdapterResult:
        self.calls.append(("apply",))
        return AdapterResult(adapter_id=self.id, applied=True)

    def verify(self, plan, context) -> AdapterResult:
        self.calls.append(("verify",))
        return AdapterResult(adapter_id=self.id, verified=True)

    def rollback(self, previous_state, context) -> AdapterResult:
        self.calls.append(("rollback",))
        return AdapterResult(adapter_id=self.id, rolled_back=True)

    def on_event(self, event: Event) -> None:
        if self.fail_on_event:
            raise RuntimeError(f"{self.id} event handler exploded")
        self.events.append(event)


class TestValueShapes:
    def test_capability_defaults(self):
        cap = AdapterCapability(id="kde", supported=True)
        assert cap.reason is None
        assert cap.version is None

    def test_capability_frozen(self):
        cap = AdapterCapability(id="kde", supported=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            cap.supported = True

    def test_result_defaults(self):
        result = AdapterResult(adapter_id="kde")
        assert result.attempted is True
        assert result.applied is False
        assert result.verified is False
        assert result.rolled_back is False
        assert result.supported is True
        assert result.warnings == ()
        assert result.errors == ()

    def test_result_failed_property(self):
        ok = AdapterResult(adapter_id="a", applied=True, verified=True)
        assert not ok.failed
        unapplied = AdapterResult(adapter_id="a", attempted=True, applied=False)
        assert unapplied.failed
        errored = AdapterResult(adapter_id="a", applied=True, errors=("x",))
        assert errored.failed

    def test_skipped_factory_marks_unsupported(self):
        result = AdapterResult.skipped("gtk", "gnome not installed")
        assert result.attempted is False
        assert result.supported is False
        assert result.warnings == ("gnome not installed",)
        assert not result.failed  # unsupported is NOT failure

    def test_result_to_dict_round_shape(self):
        payload = AdapterResult(
            adapter_id="a", applied=True, warnings=("w",), errors=("e",)
        ).to_dict()
        assert payload["adapter_id"] == "a"
        assert payload["warnings"] == ["w"]
        assert payload["errors"] == ["e"]

    def test_protocol_is_structural(self):
        assert isinstance(RecordingAdapter(), ThemeAdapter)
        assert not isinstance(object(), ThemeAdapter)


class TestAdapterRegistry:
    def test_register_preserves_order(self):
        registry = AdapterRegistry()
        a, b = RecordingAdapter("a"), RecordingAdapter("b")
        registry.register(a)
        registry.register(b)
        assert registry.ids == ("a", "b")
        assert registry.adapters == (a, b)
        assert len(registry) == 2
        assert "a" in registry

    def test_duplicate_id_rejected(self):
        registry = AdapterRegistry()
        registry.register(RecordingAdapter("dup"))
        with pytest.raises(AdapterError, match="already registered"):
            registry.register(RecordingAdapter("dup"))

    def test_adapter_without_id_rejected(self):
        class NoId:
            pass

        registry = AdapterRegistry()
        with pytest.raises(AdapterError, match="id"):
            registry.register(NoId())

    def test_get_and_is_critical_unknown_raise(self):
        registry = AdapterRegistry()
        with pytest.raises(AdapterError):
            registry.get("ghost")
        with pytest.raises(AdapterError):
            registry.is_critical("ghost")

    def test_criticality_defaults_to_false(self):
        registry = AdapterRegistry()
        registry.register(RecordingAdapter("plain"))
        assert registry.is_critical("plain") is False

    def test_criticality_read_from_adapter_attribute(self):
        registry = AdapterRegistry()
        registry.register(RecordingAdapter("core", critical=True))
        assert registry.is_critical("core") is True

    def test_explicit_criticality_overrides_attribute(self):
        registry = AdapterRegistry()
        registry.register(RecordingAdapter("forced", critical=True), critical=False)
        assert registry.is_critical("forced") is False
        registry.register(RecordingAdapter("other"), critical=True)
        assert registry.is_critical("other") is True


class TestEventForwarding:
    def test_attach_forwards_lifecycle_events_to_on_event(self):
        dispatcher = EventDispatcher()
        registry = AdapterRegistry()
        adapter = RecordingAdapter("listener")
        registry.register(adapter)
        registry.attach(dispatcher)

        dispatcher.emit(EVENT_POST_ACTIVATE, generation="g1")

        assert len(adapter.events) == 1
        assert adapter.events[0].payload == {"generation": "g1"}

    def test_adapters_without_on_event_are_ignored(self):
        dispatcher = EventDispatcher()
        registry = AdapterRegistry()

        class Silent(RecordingAdapter):
            on_event = None  # type: ignore[assignment]

        registry.register(Silent())
        registry.attach(dispatcher)
        assert dispatcher.emit(EVENT_POST_ACTIVATE) == []

    def test_handler_failure_is_aggregated_into_one_error(self):
        dispatcher = EventDispatcher()
        registry = AdapterRegistry()
        registry.register(RecordingAdapter("bad", fail_on_event=True))
        good = RecordingAdapter("good")
        registry.register(good)
        registry.attach(dispatcher)

        errors = dispatcher.emit(EVENT_POST_ACTIVATE)

        assert len(errors) == 1
        assert "bad: bad event handler exploded" in errors[0].error
        assert len(good.events) == 1  # ran despite the broken sibling

    def test_detach_stops_forwarding(self):
        dispatcher = EventDispatcher()
        registry = AdapterRegistry()
        adapter = RecordingAdapter("listener")
        registry.register(adapter)
        registry.attach(dispatcher)
        registry.detach(dispatcher)

        dispatcher.emit(EVENT_POST_ACTIVATE)

        assert adapter.events == []
