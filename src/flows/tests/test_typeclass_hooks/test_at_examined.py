"""Tests for the EXAMINE_PRE/EXAMINED reactive event pair at the LookAction seam.

Unified dispatch: ``gather_examine_extras`` (``actions.definitions.examine_extras``)
emits EXAMINE_PRE (with cancellation support) then EXAMINED, both via
``emit_event(name, payload, location=...)``. Self-targeting is expressed via
``SELF_FILTER`` rather than a scope kwarg.

This event pair used to be reachable only through the dead
``ObjectParent.at_examined``/``return_appearance`` typeclass hook (a path with zero
live callers). It is now driven exclusively through the live ``LookAction`` seam
(#3084, ADR-0213) — every test here calls ``LookAction().run(observer,
target=...)``, exactly as telnet's ``CmdLook`` and the web examine-on-click
affordance do.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.perception import LookAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import ExaminedPayload, ExaminePrePayload
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}


def _create_room(key: str = "TestRoom") -> ObjectDB:
    """Create a Room typeclass instance suitable for trigger dispatch."""
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _create_object(key: str = "TestObj", location=None) -> ObjectDB:
    """Create a plain Object typeclass instance."""
    obj = ObjectDBFactory(
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


def _look(observer: ObjectDB, target: ObjectDB):
    """Drive the live seam: ``LookAction().run(observer, target=target)``."""
    return LookAction().run(observer, target=target)


# ---------------------------------------------------------------------------
# Basic emission tests
# ---------------------------------------------------------------------------


class ExamineEventsEmitOnLookTests(TestCase):
    """Looking at an object emits EXAMINE_PRE then EXAMINED."""

    def test_returns_success_with_no_triggers(self) -> None:
        """A look succeeds (non-cancelled) when no reactive triggers are attached."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        result = _look(observer, obj)

        self.assertTrue(result.success)
        self.assertNotEqual(result.message, "")

    def test_emits_examine_pre_payload(self) -> None:
        """EXAMINE_PRE is emitted with observer and target set correctly."""
        captured: list[ExaminePrePayload] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.EXAMINE_PRE:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            _look(observer, obj)
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
        observer.location = room

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.EXAMINED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            _look(observer, obj)
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
        observer.location = room

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            order.append(event_name)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            _look(observer, obj)
        finally:
            emit_mod.emit_event = original

        self.assertIn(EventName.EXAMINE_PRE, order)
        self.assertIn(EventName.EXAMINED, order)
        self.assertLess(order.index(EventName.EXAMINE_PRE), order.index(EventName.EXAMINED))

    def test_self_targeted_trigger_fires_on_examine_pre(self) -> None:
        """A trigger on the examined object fires when it is looked at."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=obj,
        )

        # Empty message because the cancel flow fired (prior contract).
        result = _look(observer, obj)
        self.assertEqual(result.message, "")

    def test_room_trigger_fires_on_examine_pre(self) -> None:
        """A trigger on the room fires when an object inside it is looked at."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            flow_definition=cancel_flow,
            target=room,
        )

        result = _look(observer, obj)
        self.assertEqual(result.message, "")

    def test_look_at_character_target_also_emits(self) -> None:
        """The event pair fires identically for a Character target (via ObjectParent MRO)."""
        room = _create_room()
        target = CharacterFactory()
        target.location = room
        observer = CharacterFactory()
        observer.location = room

        result = _look(observer, target)

        self.assertTrue(result.success)


# ---------------------------------------------------------------------------
# Cancellation tests
# ---------------------------------------------------------------------------


class ExamineCancellationTests(TestCase):
    """CANCEL_EVENT on EXAMINE_PRE stops EXAMINED from firing and yields empty output."""

    def test_cancel_yields_success_with_empty_message(self) -> None:
        """A cancelled look is the prior contract: success, but the command shows nothing."""
        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=obj,
        )

        result = _look(observer, obj)

        self.assertTrue(result.success)
        self.assertEqual(result.message, "")

    def test_cancel_suppresses_examined_event(self) -> None:
        """When EXAMINE_PRE is cancelled, EXAMINED must not fire."""
        examined_fired: list[bool] = []

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=obj,
        )

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.EXAMINED:
                examined_fired.append(True)
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = capturing_emit
        try:
            _look(observer, obj)
        finally:
            emit_mod.emit_event = original

        self.assertEqual(examined_fired, [], "EXAMINED fired after cancellation")

    def test_no_cancel_examined_fires_exactly_once(self) -> None:
        """Without cancellation, EXAMINED fires exactly once per look."""
        examined_count: list[int] = [0]

        room = _create_room()
        obj = _create_object(location=room)
        observer = CharacterFactory()
        observer.location = room

        import flows.emit as emit_mod

        original = emit_mod.emit_event

        def counting_emit(event_name, payload, **kwargs):
            if event_name == EventName.EXAMINED:
                examined_count[0] += 1
            return original(event_name, payload, **kwargs)

        emit_mod.emit_event = counting_emit
        try:
            result = _look(observer, obj)
        finally:
            emit_mod.emit_event = original

        self.assertTrue(result.success)
        self.assertEqual(examined_count[0], 1)
