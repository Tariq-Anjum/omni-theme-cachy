"""Unit tests for core.events: lifecycle event names, dispatcher semantics."""

from __future__ import annotations

import pytest

from core.events import (
    EVENT_POST_ACTIVATE,
    EVENT_POST_CORE_ACTIVATE,
    EVENT_POST_ROLLBACK,
    EVENT_POST_VERIFY,
    EVENT_PRE_ACTIVATE,
    EVENT_PRE_ROLLBACK,
    LIFECYCLE_EVENTS,
    Event,
    EventDispatcher,
)


class TestEventNames:
    def test_lifecycle_set_is_complete(self):
        assert set(LIFECYCLE_EVENTS) == {
            EVENT_PRE_ACTIVATE,
            EVENT_POST_CORE_ACTIVATE,
            EVENT_POST_VERIFY,
            EVENT_POST_ACTIVATE,
            EVENT_PRE_ROLLBACK,
            EVENT_POST_ROLLBACK,
        }

    def test_original_three_names_are_preserved(self):
        # Compatibility: pre_activate / post_activate / post_rollback
        assert EVENT_PRE_ACTIVATE == "pre_activate"
        assert EVENT_POST_ACTIVATE == "post_activate"
        assert EVENT_POST_ROLLBACK == "post_rollback"


class TestEvent:
    def test_payload_copied_on_construction(self):
        payload = {"a": 1}
        event = Event(name="e", payload=payload)
        payload["a"] = 999
        assert event.payload == {"a": 1}

    def test_get_helper(self):
        event = Event(name="e", payload={"x": 5})
        assert event.get("x") == 5
        assert event.get("missing", "d") == "d"

    def test_frozen(self):
        event = Event(name="e")
        with pytest.raises(AttributeError):
            event.name = "other"


class TestDispatcher:
    def test_subscribe_and_emit_delivers_event(self):
        seen = []
        d = EventDispatcher()
        d.subscribe("pre_activate", seen.append, owner="recorder")
        errors = d.emit("pre_activate", theme="alpha", generation="g1")

        assert errors == []
        assert len(seen) == 1
        assert seen[0].name == "pre_activate"
        assert seen[0].payload == {"theme": "alpha", "generation": "g1"}

    def test_subscribers_run_in_registration_order(self):
        order = []
        d = EventDispatcher()
        d.subscribe("e", lambda ev: order.append("first"))
        d.subscribe("e", lambda ev: order.append("second"))
        d.emit("e")
        assert order == ["first", "second"]

    def test_unsubscribe_stops_delivery(self):
        seen = []
        d = EventDispatcher()
        cb = seen.append
        d.subscribe("e", cb)
        assert d.unsubscribe("e", cb) is True
        assert d.unsubscribe("e", cb) is False
        d.emit("e")
        assert seen == []

    def test_unsubscribe_owner_removes_only_that_owner(self):
        seen = []
        d = EventDispatcher()
        d.subscribe("e", lambda ev: seen.append("a"), owner="a")
        d.subscribe("e", lambda ev: seen.append("b"), owner="b")
        assert d.unsubscribe_owner("a") == 1
        d.emit("e")
        assert [label for label in seen] == ["b"]

    def test_raising_subscriber_is_captured_not_raised(self):
        d = EventDispatcher()

        def boom(event):
            raise ValueError("listener exploded")

        d.subscribe("e", boom, owner="boom")
        errors = d.emit("e", k=1)
        assert len(errors) == 1
        assert errors[0].subscriber == "boom"
        assert "listener exploded" in errors[0].error

    def test_broken_subscriber_does_not_block_others(self):
        seen = []
        d = EventDispatcher()
        d.subscribe("e", lambda ev: (_ for _ in ()).throw(RuntimeError("x")), owner="bad")
        d.subscribe("e", seen.append, owner="good")
        errors = d.emit("e")
        assert len(errors) == 1
        assert len(seen) == 1

    def test_emit_to_unknown_event_is_harmless(self):
        d = EventDispatcher()
        assert d.emit("nobody-listens") == []

    def test_non_callable_subscription_rejected(self):
        d = EventDispatcher()
        with pytest.raises(TypeError):
            d.subscribe("e", "not-callable")

    def test_subscriber_count(self):
        d = EventDispatcher()
        d.subscribe("e", lambda ev: None)
        assert d.subscriber_count("e") == 1
        assert d.subscriber_count("other") == 0
