"""CANCEL_EVENT flow step: trigger flow marks the FlowStack cancelled."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class CancelEventStepTests(TestCase):
    def test_cancel_step_marks_stack_cancelled(self) -> None:
        """A trigger flow with CANCEL_EVENT sets ``stack.was_cancelled()``."""
        character = CharacterFactory()
        room = _create_room()
        character.location = room
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow,
            target=character,
        )
        payload = DamagePreApplyPayload(
            target=character,
            amount=10,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
        )
        stack = emit_event(EventNames.DAMAGE_PRE_APPLY, payload, location=room)
        self.assertTrue(stack.was_cancelled())
