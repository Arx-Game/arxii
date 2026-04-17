"""CANCEL_EVENT flow step: trigger flow sets DispatchResult.cancelled=True."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.consts import FlowActionChoices
from flows.events.names import EventNames
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory


class CancelEventStepTests(TestCase):
    def test_cancel_step_sets_cancelled(self) -> None:
        character = CharacterFactory()
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
        result = character.trigger_handler.dispatch(
            EventNames.DAMAGE_PRE_APPLY,
            payload,
        )
        self.assertTrue(result.cancelled)
