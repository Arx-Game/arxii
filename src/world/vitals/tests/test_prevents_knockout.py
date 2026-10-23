"""A grace condition stops the knockout roll while it holds (#4584).

``prevents_knockout`` is read by ``_process_knockout_tier``, the one place a PC's
knockout roll happens: an ``UNTIL_USED`` grace stops one knockout and ends, a
``ROUNDS`` grace stops every knockout while it lasts, and a grace is only used when a
knockout roll would actually happen (inside the knockout band). NPC opponents have no
knockout roll, so the flag has nothing to stop on them.

The grace templates are named unlike any seed: the field designates them.
"""

from django.test import TestCase, override_settings

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionInstance
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import get_vitals_consequence_config, process_damage_consequences


@override_settings(SEED_SAMPLE_CONTENT=True)  # Endurance CheckType gates on #2698
class PreventsKnockoutTests(TestCase):
    """Every test mutates vitals or spends a grace, so the rows are rebuilt in setUp."""

    def setUp(self) -> None:
        self.vitals = CharacterVitalsFactory(health=10, max_health=100)
        self.sheet = self.vitals.character_sheet
        self.character = self.sheet.character

        self.failure_outcome = CheckOutcomeFactory(name="Grace-KO-Failure", success_level=-1)
        consequence = ConsequenceFactory(outcome_tier=self.failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=UnconsciousConditionFactory(),
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])

    def _grace(self, duration_type: str, name: str) -> ConditionInstance:
        template = ConditionTemplateFactory(
            name=name, prevents_knockout=True, default_duration_type=duration_type
        )
        return ConditionInstanceFactory(condition=template, target=self.character)

    def _hit(self):
        with force_check_outcome(self.failure_outcome):
            return process_damage_consequences(
                character_sheet=self.sheet, damage_dealt=5, damage_type=None
            )

    def test_a_once_only_grace_stops_one_knockout_and_ends(self) -> None:
        grace_pk = self._grace(DurationType.UNTIL_USED, "Last Breath Grace 4584").pk

        first = self._hit()

        self.assertFalse(first.knocked_out)
        self.assertFalse(ConditionInstance.objects.filter(pk=grace_pk).exists())

        second = self._hit()

        self.assertTrue(second.knocked_out)

    def test_a_rounds_grace_stops_every_knockout_while_it_holds(self) -> None:
        grace_pk = self._grace(DurationType.ROUNDS, "Iron Will Grace 4584").pk

        first = self._hit()
        second = self._hit()

        self.assertFalse(first.knocked_out)
        self.assertFalse(second.knocked_out)
        self.assertTrue(ConditionInstance.objects.filter(pk=grace_pk).exists())

    def test_a_grace_is_not_spent_outside_the_knockout_band(self) -> None:
        self.vitals.health = 80
        self.vitals.save(update_fields=["health"])
        grace_pk = self._grace(DurationType.UNTIL_USED, "Unneeded Grace 4584").pk

        result = self._hit()

        self.assertFalse(result.knocked_out)
        self.assertTrue(ConditionInstance.objects.filter(pk=grace_pk).exists())

    def test_a_suppressed_grace_does_not_stop_the_knockout(self) -> None:
        grace = self._grace(DurationType.UNTIL_USED, "Smothered Grace 4584")
        grace.is_suppressed = True
        grace.save(update_fields=["is_suppressed"])

        result = self._hit()

        self.assertTrue(result.knocked_out)
        self.assertTrue(ConditionInstance.objects.filter(pk=grace.pk).exists())

    def test_without_a_grace_the_knockout_lands(self) -> None:
        result = self._hit()

        self.assertTrue(result.knocked_out)
