"""Tests for emit_event: ROOM-first dispatch order with cancellation propagation.

Task 24: emit_event dispatches ROOM before PERSONAL.  Room-scope triggers
get first shot at cancellation; if the stack is marked cancelled after ROOM
dispatch, PERSONAL dispatch is skipped entirely.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import TriggerScope
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from flows.flow_stack import FlowStack
from world.conditions.factories import ReactiveConditionFactory


def _damage_payload(target) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(
        target=target,
        amount=10,
        damage_type="fire",
        source=DamageSource(type="character", ref=None),
    )


def _create_room() -> ObjectDB:
    """Create a Room typeclass instance suitable for trigger dispatch."""
    return ObjectDB.objects.create(
        db_key="TestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_modify_flow(field: str, value: int, op: str = "set") -> object:
    """Return a FlowDefinition with a single MODIFY_PAYLOAD step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": field, "op": op, "value": value},
    )
    return flow


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


class DualEmissionBothFireTests(TestCase):
    """ROOM + PERSONAL scope both fire when neither cancels."""

    def test_dual_emission_both_fire(self) -> None:
        char = CharacterFactory()
        room = _create_room()

        # ROOM-scoped trigger: multiply amount by 3
        room_flow = _make_modify_flow("amount", 3, "multiply")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=room_flow,
            target=room,
            scope=TriggerScope.ROOM,
        )

        # PERSONAL-scoped trigger: add 100 to amount
        personal_flow = _make_modify_flow("amount", 100, "add")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=personal_flow,
            target=char,
            scope=TriggerScope.PERSONAL,
        )

        payload = _damage_payload(char)
        # amount starts at 10; ROOM multiplies → 30; PERSONAL adds 100 → 130
        emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=room,
        )

        self.assertEqual(payload.amount, 130)


class RoomCancelSkipsPersonalTests(TestCase):
    """When a ROOM-scoped flow cancels, PERSONAL dispatch is skipped."""

    def test_room_cancel_skips_personal(self) -> None:
        char = CharacterFactory()
        room = _create_room()

        # ROOM-scoped trigger: cancel event
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=cancel_flow,
            target=room,
            scope=TriggerScope.ROOM,
        )

        # PERSONAL-scoped trigger: set amount to 0 (sentinel — should NOT run)
        sentinel_flow = _make_modify_flow("amount", 0, "set")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=sentinel_flow,
            target=char,
            scope=TriggerScope.PERSONAL,
        )

        payload = _damage_payload(char)
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=room,
        )

        # Cancellation happened at ROOM scope
        self.assertTrue(stack.was_cancelled())
        # PERSONAL sentinel did NOT run — amount stays at 10
        self.assertEqual(payload.amount, 10)


class PersonalOnlyTests(TestCase):
    """emit_event with personal_target only fires PERSONAL scope."""

    def test_personal_only(self) -> None:
        char = CharacterFactory()

        flow = _make_modify_flow("amount", 5, "add")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow,
            target=char,
            scope=TriggerScope.PERSONAL,
        )

        payload = _damage_payload(char)
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=None,
        )

        self.assertIsNotNone(stack)
        self.assertEqual(stack.owner.pk, char.pk)
        self.assertEqual(payload.amount, 15)


class RoomOnlyTests(TestCase):
    """emit_event with room only fires ROOM scope."""

    def test_room_only(self) -> None:
        room = _create_room()

        flow = _make_modify_flow("amount", 2, "multiply")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow,
            target=room,
            scope=TriggerScope.ROOM,
        )

        # Use a dummy character as target in the payload only — no personal dispatch
        char = CharacterFactory()
        payload = _damage_payload(char)
        stack = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=None,
            room=room,
        )

        self.assertIsNotNone(stack)
        self.assertEqual(stack.owner.pk, room.pk)
        self.assertEqual(payload.amount, 20)


class ParentStackNestingTests(TestCase):
    """When parent_stack is supplied, both scopes dispatch inside nested()."""

    def test_parent_stack_nesting_respected(self) -> None:
        char = CharacterFactory()
        room = _create_room()

        # Attach triggers so dispatch actually runs something
        flow = _make_modify_flow("amount", 1, "add")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow,
            target=room,
            scope=TriggerScope.ROOM,
        )
        flow2 = _make_modify_flow("amount", 1, "add")
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow2,
            target=char,
            scope=TriggerScope.PERSONAL,
        )

        parent = FlowStack(owner=None, originating_event="outer")
        payload = _damage_payload(char)
        result = emit_event(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
            personal_target=char,
            room=room,
            parent_stack=parent,
        )

        # When parent_stack is supplied, result_stack is the parent_stack
        self.assertIs(result, parent)
        # Depth returns to 1 after both nested() contexts exit
        self.assertEqual(parent.depth, 1)
