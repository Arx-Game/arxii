"""Dispatch tests: additional_filter_condition gates whether a trigger fires."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import DamageAppliedPayload, DamageSource
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step.

    Used as a detectable side effect: when this trigger fires, the
    returned FlowStack is marked cancelled.
    """
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


class DispatchTests(TestCase):
    def test_filter_mismatch_skips(self) -> None:
        character = CharacterFactory()
        room = _create_room()
        character.location = room
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
            target=character,
            flow_definition=_make_cancel_flow(),
        )
        payload = DamageAppliedPayload(
            target=character,
            amount_dealt=5,
            damage_type="cold",
            source=DamageSource(type="character", ref=None),
            hp_after=45,
        )
        stack = emit_event(EventNames.DAMAGE_APPLIED, payload, location=room)
        # Filter did not match → trigger did not fire → stack not cancelled.
        self.assertFalse(stack.was_cancelled())

    def test_filter_match_fires(self) -> None:
        character = CharacterFactory()
        room = _create_room()
        character.location = room
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
            target=character,
            flow_definition=_make_cancel_flow(),
        )
        payload = DamageAppliedPayload(
            target=character,
            amount_dealt=5,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
            hp_after=45,
        )
        stack = emit_event(EventNames.DAMAGE_APPLIED, payload, location=room)
        # Filter matched → trigger fired → CANCEL_EVENT marked the stack cancelled.
        self.assertTrue(stack.was_cancelled())
