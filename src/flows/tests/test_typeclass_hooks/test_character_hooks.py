"""Tests for Character typeclass hooks: at_attacked and at_pre_move.

Unified dispatch: the hooks call ``emit_event(name, payload, location=...)``
and reactive triggers on the location or its contents get one shared
FlowStack. Self-targeting is expressed via ``SELF_FILTER`` rather than a
scope kwarg.
"""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import AttackLandedPayload, MovePreDepartPayload
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}
CHAR_SELF_FILTER = {"path": "character", "op": "==", "value": "self"}


def _create_room(key: str = "TestRoom") -> ObjectDB:
    """Create a Room typeclass instance suitable for trigger dispatch."""
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


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


def _make_modify_flow(field: str, value, op: str = "set") -> object:
    """Return a FlowDefinition with a single MODIFY_PAYLOAD step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": field, "op": op, "value": value},
    )
    return flow


# ---------------------------------------------------------------------------
# at_attacked tests
# ---------------------------------------------------------------------------


class AtAttackedEmitsAttackLandedTests(TestCase):
    """at_attacked emits ATTACK_LANDED at self.location."""

    def test_self_targeted_trigger_fires_on_at_attacked(self) -> None:
        """A trigger on the defender fires when at_attacked is called."""
        char = CharacterFactory()
        room = _create_room()
        char.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_LANDED,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=char,
        )

        attacker = CharacterFactory()
        weapon = MagicMock()
        damage_result = MagicMock()
        action = MagicMock()

        # Should not raise; the cancel flow fired on the unified stack
        char.at_attacked(attacker, weapon, damage_result, action)

    def test_room_trigger_fires_on_at_attacked(self) -> None:
        """A trigger attached to the room fires when at_attacked is called."""
        char = CharacterFactory()
        room = _create_room()
        char.location = room

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.ATTACK_LANDED,
            flow_definition=cancel_flow,
            target=room,
        )

        attacker = CharacterFactory()
        weapon = MagicMock()
        damage_result = MagicMock()
        action = MagicMock()

        # Should not raise; the room trigger fired
        char.at_attacked(attacker, weapon, damage_result, action)

    def test_at_attacked_payload_fields(self) -> None:
        """Payload passed to emit_event has correct attacker/target/etc fields."""
        captured: list[AttackLandedPayload] = []

        char = CharacterFactory()
        room = _create_room()
        char.location = room
        attacker = CharacterFactory()
        weapon = MagicMock(name="sword")
        damage_result = MagicMock(name="dmg")
        action = MagicMock(name="act")

        import flows.emit as emit_mod
        import typeclasses.characters as chars_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.ATTACK_LANDED:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        chars_mod.emit_event = capturing_emit
        try:
            char.at_attacked(attacker, weapon, damage_result, action)
        finally:
            chars_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIs(p.attacker, attacker)
        self.assertIs(p.target, char)
        self.assertIs(p.weapon, weapon)
        self.assertIs(p.damage_result, damage_result)
        self.assertIs(p.action, action)


# ---------------------------------------------------------------------------
# at_pre_move tests
# ---------------------------------------------------------------------------


class AtPreMoveEmitsMovePreDepartTests(TestCase):
    """at_pre_move emits MOVE_PRE_DEPART at the origin location."""

    def test_pre_move_emits_event_and_returns_true(self) -> None:
        """at_pre_move returns True when no trigger cancels."""
        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        result = char.at_pre_move(destination)

        self.assertTrue(result)

    def test_self_targeted_trigger_fires_on_at_pre_move(self) -> None:
        """A trigger on the moving character fires when at_pre_move is called."""
        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        # Non-cancelling flow to confirm it fires without side effects
        sentinel_flow = _make_modify_flow("exit_used", "test_exit", op="set")
        ReactiveConditionFactory(
            event_name=EventName.MOVE_PRE_DEPART,
            filter_condition=CHAR_SELF_FILTER,
            flow_definition=sentinel_flow,
            target=char,
        )

        result = char.at_pre_move(destination)

        # Trigger fired (MODIFY_PAYLOAD on exit_used), movement not cancelled
        self.assertTrue(result)

    def test_at_pre_move_payload_fields(self) -> None:
        """Payload passed to emit_event has correct character/origin/destination."""
        captured: list[MovePreDepartPayload] = []

        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        import flows.emit as emit_mod
        import typeclasses.characters as chars_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            if event_name == EventName.MOVE_PRE_DEPART:
                captured.append(payload)
            return original(event_name, payload, **kwargs)

        chars_mod.emit_event = capturing_emit
        try:
            char.at_pre_move(destination)
        finally:
            chars_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIs(p.character, char)
        self.assertIs(p.origin, origin)
        self.assertIs(p.destination, destination)


class AtPreMoveCancelledByReactiveStackTests(TestCase):
    """at_pre_move returns False when the reactive stack cancels."""

    def test_cancel_event_on_move_pre_depart_returns_false(self) -> None:
        """When a reactive trigger cancels MOVE_PRE_DEPART, at_pre_move returns False."""
        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.MOVE_PRE_DEPART,
            filter_condition=CHAR_SELF_FILTER,
            flow_definition=cancel_flow,
            target=char,
        )

        result = char.at_pre_move(destination)

        self.assertFalse(result)

    def test_room_cancel_on_move_pre_depart_returns_false(self) -> None:
        """When a room-attached trigger cancels MOVE_PRE_DEPART, at_pre_move returns False."""
        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.MOVE_PRE_DEPART,
            flow_definition=cancel_flow,
            target=origin,
        )

        result = char.at_pre_move(destination)

        self.assertFalse(result)


class AtPreMoveSuperReturnsFalseTests(TestCase):
    """at_pre_move returns False and skips emission when super() returns False."""

    def test_super_false_skips_emission(self) -> None:
        """If super().at_pre_move returns False, we return False without emitting."""
        captured_emits: list[str] = []

        char = CharacterFactory()
        origin = _create_room("Origin")
        destination = _create_room("Destination")
        char.location = origin

        import flows.emit as emit_mod
        import typeclasses.characters as chars_mod

        original = emit_mod.emit_event

        def capturing_emit(event_name, payload, **kwargs):
            captured_emits.append(event_name)
            return original(event_name, payload, **kwargs)

        # Temporarily make the DefaultObject.at_pre_move return False
        from evennia.objects import objects as evennia_objects

        original_at_pre_move = evennia_objects.DefaultObject.at_pre_move

        def false_pre_move(self_obj, destination, move_type="move", **kwargs):
            return False

        evennia_objects.DefaultObject.at_pre_move = false_pre_move
        chars_mod.emit_event = capturing_emit
        try:
            result = char.at_pre_move(destination)
        finally:
            evennia_objects.DefaultObject.at_pre_move = original_at_pre_move
            chars_mod.emit_event = original

        self.assertFalse(result)
        # MOVE_PRE_DEPART should NOT have been emitted
        self.assertNotIn(EventName.MOVE_PRE_DEPART, captured_emits)
