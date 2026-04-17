"""MODIFY_PAYLOAD flow step: mutates a field on the current payload."""

import dataclasses

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.consts import FlowActionChoices
from flows.events.names import EventNames
from flows.events.payloads import (
    DamageAppliedPayload,
    DamagePreApplyPayload,
    DamageSource,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory


class ModifyPayloadStepTests(TestCase):
    def test_modify_payload_multiplies_amount(self) -> None:
        """Fire-vuln scar: on damage_pre_apply, multiply amount by 2."""
        character = CharacterFactory()
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount", "op": "multiply", "value": 2},
        )
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_PRE_APPLY,
            flow_definition=flow,
            target=character,
            filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
        )
        payload = DamagePreApplyPayload(
            target=character,
            amount=10,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
        )
        character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 20)

    def test_modify_payload_set_op(self) -> None:
        """Op 'set' replaces the field's value."""
        character = CharacterFactory()
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount", "op": "set", "value": 0},
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
        character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 0)

    def test_modify_payload_add_op(self) -> None:
        """Op 'add' adds the value to the field."""
        character = CharacterFactory()
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount", "op": "add", "value": 5},
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
        character.trigger_handler.dispatch(EventNames.DAMAGE_PRE_APPLY, payload)
        self.assertEqual(payload.amount, 15)

    def test_modify_payload_rejects_frozen_post_event(self) -> None:
        """POST events use frozen dataclasses; setattr raises FrozenInstanceError."""
        character = CharacterFactory()
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "amount_dealt", "op": "set", "value": 0},
        )
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            flow_definition=flow,
            target=character,
        )
        payload = DamageAppliedPayload(
            target=character,
            amount_dealt=10,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
            hp_after=45,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            character.trigger_handler.dispatch(EventNames.DAMAGE_APPLIED, payload)
