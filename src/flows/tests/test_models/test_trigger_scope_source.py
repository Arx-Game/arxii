from django.core.exceptions import ValidationError
from django.test import TestCase

from flows.factories import TriggerDefinitionFactory, TriggerFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionStageFactory


class TriggerScopeSourceTests(TestCase):
    def test_trigger_requires_source_condition(self) -> None:
        trigger_def = TriggerDefinitionFactory()
        with self.assertRaises(ValidationError):
            t = TriggerFactory.build(
                trigger_definition=trigger_def,
                source_condition=None,
            )
            t.full_clean()

    def test_condition_cascade_removes_triggers(self) -> None:
        condition = ConditionInstanceFactory()
        trigger = TriggerFactory(
            source_condition=condition,
        )
        trigger_pk = trigger.pk
        condition.delete()
        from flows.models import Trigger

        self.assertFalse(Trigger.objects.filter(pk=trigger_pk).exists())

    def test_stage_must_belong_to_condition_template(self) -> None:
        condition = ConditionInstanceFactory()
        other_stage = ConditionStageFactory()  # different template via SubFactory
        with self.assertRaises(ValidationError):
            t = TriggerFactory.build(
                source_condition=condition,
                source_stage=other_stage,
            )
            t.full_clean()
