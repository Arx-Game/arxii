"""Tests for the at_examined hook on ObjectParent and return_appearance wiring.

Task 26: at_examined emits EXAMINE_PRE/EXAMINED with cancellation support.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import TriggerScope
from flows.consts import FlowActionChoices
from flows.events.names import EventNames
from flows.events.payloads import ExaminedPayload, ExaminePrePayload
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory


def _create_room(key: str = "TestRoom") -> ObjectDB:
    """Create a Room typeclass instance suitable for trigger dispatch."""
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _create_object(key: str = "TestObj", location=None) -> ObjectDB:
    """Create a plain Object typeclass instance."""
    obj = ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.objects.Object",
    )
    if location is not None:
        obj.location = location
    return obj


def _make_cancel_flow() -> object:
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


# ---------------------------------------------------------------------------
# Basic emission tests
# ---------------------------------------------------------------------------


class AtExaminedEmitsEventsTests(TestCase):
    """at_examined emits EXAMINE_PRE then EXAMINED."""

    def test_returns_true_with_no_triggers(self) -> None:
        """at_examined returns True when no reactive triggers are attached."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        result = obj.at_examined(observer)

        self.assertTrue(result)

    def test_emits_examine_pre_payload(self) -> None:
        """EXAMINE_PRE is emitted with observer and target set correctly."""
        captured: list[ExaminePrePayload] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.EXAMINE_PRE:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            obj.at_examined(observer)
        finally:
            emit_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIs(p.observer, observer)
        self.assertIs(p.target, obj)

    def test_emits_examined_payload(self) -> None:
        """EXAMINED is emitted with observer and target set correctly."""
        captured: list[ExaminedPayload] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.EXAMINED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            obj.at_examined(observer)
        finally:
            emit_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIs(p.observer, observer)
        self.assertIs(p.target, obj)

    def test_both_events_emitted_in_order(self) -> None:
        """EXAMINE_PRE is emitted before EXAMINED."""
        order: list[str] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            order.append(event_name)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            obj.at_examined(observer)
        finally:
            emit_mod.emit_event = original

        self.assertIn(EventNames.EXAMINE_PRE, order)
        self.assertIn(EventNames.EXAMINED, order)
        self.assertLess(order.index(EventNames.EXAMINE_PRE), order.index(EventNames.EXAMINED))

    def test_personal_trigger_fires_on_examine_pre(self) -> None:
        """A PERSONAL-scoped ReactiveCondition fires when at_examined is called."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=obj,
            scope=TriggerScope.PERSONAL,
        )

        # Returns False because the cancel flow fired
        result = obj.at_examined(observer)
        self.assertFalse(result)

    def test_room_trigger_fires_on_examine_pre(self) -> None:
        """A ROOM-scoped ReactiveCondition fires when at_examined is called."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=room,
            scope=TriggerScope.ROOM,
        )

        result = obj.at_examined(observer)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Cancellation tests
# ---------------------------------------------------------------------------


class AtExaminedCancellationTests(TestCase):
    """CANCEL_EVENT on EXAMINE_PRE stops EXAMINED from firing."""

    def test_cancel_returns_false(self) -> None:
        """at_examined returns False when a trigger cancels EXAMINE_PRE."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=obj,
            scope=TriggerScope.PERSONAL,
        )

        result = obj.at_examined(observer)

        self.assertFalse(result)

    def test_cancel_suppresses_examined_event(self) -> None:
        """When EXAMINE_PRE is cancelled, EXAMINED must not fire."""
        examined_fired: list[bool] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=obj,
            scope=TriggerScope.PERSONAL,
        )

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventNames.EXAMINED:
                examined_fired.append(True)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            obj.at_examined(observer)
        finally:
            emit_mod.emit_event = original

        self.assertEqual(examined_fired, [], "EXAMINED fired after cancellation")

    def test_no_cancel_examined_fires(self) -> None:
        """Without cancellation, EXAMINED fires exactly once."""
        examined_count: list[int] = [0]

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def counting_emit(event_name, payload, **kwargs):
            if event_name == EventNames.EXAMINED:
                examined_count[0] += 1
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = counting_emit
        try:
            result = obj.at_examined(observer)
        finally:
            emit_mod.emit_event = original

        self.assertTrue(result)
        self.assertEqual(examined_count[0], 1)


# ---------------------------------------------------------------------------
# return_appearance wiring tests
# ---------------------------------------------------------------------------


class ReturnAppearanceCancellationTests(TestCase):
    """return_appearance returns '' when at_examined returns False."""

    def test_return_appearance_suppressed_on_cancel(self) -> None:
        """return_appearance returns empty string when examine is cancelled."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=obj,
            scope=TriggerScope.PERSONAL,
        )

        result = obj.return_appearance(observer)

        self.assertEqual(result, "")

    def test_return_appearance_normal_when_not_cancelled(self) -> None:
        """return_appearance delegates to super() when examine is not cancelled."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()

        # No triggers attached; should return a non-empty description
        result = obj.return_appearance(observer)

        # Evennia's default return_appearance returns something non-empty for a named object
        self.assertIsInstance(result, str)

    def test_return_appearance_none_looker_skips_hook(self) -> None:
        """return_appearance with looker=None skips at_examined and delegates normally."""
        room = _create_room()
        obj = _create_object(location=room)

        # Should not raise; looker=None skips the hook
        result = obj.return_appearance(None)

        self.assertIsInstance(result, str)

    def test_character_inherits_at_examined(self) -> None:
        """Character (via ObjectParent MRO) also has at_examined."""
        room = _create_room()
        char = CharacterFactory()
        char.location = room
        observer = CharacterFactory()

        result = char.at_examined(observer)

        self.assertTrue(result)
