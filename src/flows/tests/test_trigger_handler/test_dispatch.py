from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.events.names import EventNames
from flows.events.payloads import DamageAppliedPayload, DamageSource
from world.conditions.factories import ReactiveConditionFactory


class DispatchTests(TestCase):
    def test_filter_mismatch_skips(self) -> None:
        character = CharacterFactory()
        ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
            target=character,
        )
        payload = DamageAppliedPayload(
            target=character,
            amount_dealt=5,
            damage_type="cold",
            source=DamageSource(type="character", ref=None),
            hp_after=45,
        )
        result = character.trigger_handler.dispatch(EventNames.DAMAGE_APPLIED, payload)
        self.assertEqual(result.fired, [])

    def test_filter_match_fires(self) -> None:
        character = CharacterFactory()
        trigger = ReactiveConditionFactory(
            event_name=EventNames.DAMAGE_APPLIED,
            filter_condition={"path": "damage_type", "op": "==", "value": "fire"},
            target=character,
        )
        payload = DamageAppliedPayload(
            target=character,
            amount_dealt=5,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
            hp_after=45,
        )
        result = character.trigger_handler.dispatch(EventNames.DAMAGE_APPLIED, payload)
        self.assertEqual(result.fired, [trigger.pk])
