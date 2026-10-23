"""Tests for spend_condition_use: a once-only (UNTIL_USED) condition ends when used (#4584)."""

from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.constants import EventName
from flows.factories import FlowDefinitionFactory, TriggerDefinitionFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import apply_condition, spend_condition_use


def _character_in_room():
    room = ObjectDBFactory(db_key="Spend Room 4584", db_typeclass_path="typeclasses.rooms.Room")
    char = CharacterFactory()
    char.location = room
    return char


class SpendConditionUseTests(TestCase):
    def setUp(self) -> None:
        self.target = _character_in_room()
        self.once_only = ConditionTemplateFactory(
            name="Steadying Word 4584",
            default_duration_type=DurationType.UNTIL_USED,
        )

    def test_an_until_used_instance_ends_and_announces_its_removal(self) -> None:
        inst = ConditionInstanceFactory(target=self.target, condition=self.once_only)
        old_pk = inst.pk

        with patch("world.conditions.services.emit_event") as mock_emit:
            spent = spend_condition_use(inst)

        self.assertTrue(spent)
        self.assertFalse(ConditionInstance.objects.filter(pk=old_pk).exists())
        removed = [
            c.args[1] for c in mock_emit.call_args_list if c.args[0] == EventName.CONDITION_REMOVED
        ]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0].instance_id, old_pk)

    def test_a_lasting_instance_is_not_spent(self) -> None:
        lasting = ConditionTemplateFactory(
            name="Lasting Word 4584", default_duration_type=DurationType.ROUNDS
        )
        inst = ConditionInstanceFactory(target=self.target, condition=lasting)

        self.assertFalse(spend_condition_use(inst))
        self.assertTrue(ConditionInstance.objects.filter(pk=inst.pk).exists())

    def test_spending_twice_is_harmless(self) -> None:
        inst = ConditionInstanceFactory(target=self.target, condition=self.once_only)

        self.assertTrue(spend_condition_use(inst))
        self.assertFalse(spend_condition_use(inst))

    def test_a_spent_wards_triggers_stop_firing_before_commit(self) -> None:
        trigger_def = TriggerDefinitionFactory(
            name="Spend td 4584",
            event_name=EventName.DAMAGE_APPLIED,
            flow_definition=FlowDefinitionFactory(name="Spend flow 4584"),
        )
        self.once_only.reactive_triggers.add(trigger_def)
        result = apply_condition(target=self.target, condition=self.once_only)
        handler = self.target.trigger_handler
        self.assertEqual(len(handler.triggers_for(EventName.DAMAGE_APPLIED)), 1)

        with transaction.atomic():
            self.assertTrue(spend_condition_use(result.instance))
            self.assertEqual(handler.triggers_for(EventName.DAMAGE_APPLIED), [])
