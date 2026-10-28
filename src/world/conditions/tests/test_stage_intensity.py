"""``ConditionStage.intensity_per_round`` and the never-from-failures rule (#4739).

U-keep: these pin a model ``clean()`` refusal that the admin form surfaces; the
per-round feed that reads the field is covered by its own journey.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SurgeDegreeBandFactory, SurgeTuningFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.traits.factories import CheckOutcomeFactory


class IntensityPerRoundTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ConditionTemplateFactory(name="Stage Intensity Fury")
        cls.tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        cls.failure = CheckOutcomeFactory(name="Stage Intensity Failure", success_level=-1)
        cls.success = CheckOutcomeFactory(name="Stage Intensity Success", success_level=2)

    def test_defaults_to_zero(self) -> None:
        stage = ConditionStageFactory(condition=self.template)
        self.assertEqual(stage.intensity_per_round, 0)

    def test_clean_refuses_positive_when_a_failure_band_carries_the_template(self) -> None:
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.failure, condition=self.template)
        stage = ConditionStageFactory(condition=self.template)
        stage.intensity_per_round = 2
        with self.assertRaises(ValidationError) as ctx:
            stage.clean()
        self.assertIn("intensity_per_round", ctx.exception.message_dict)

    def test_clean_allows_positive_when_only_success_bands_carry_it(self) -> None:
        SurgeDegreeBandFactory(tuning=self.tuning, outcome=self.success, condition=self.template)
        stage = ConditionStageFactory(condition=self.template)
        stage.intensity_per_round = 2
        stage.clean()
