"""A once-only (UNTIL_USED) condition that helped a combat-side roll ends after it (#4584).

``consider_opponent`` stands for the sites that roll through ``collect_check_modifiers``
then a plain ``perform_check``; the mechanical guard in
``world.checks.tests.test_spend_contributing_conditions`` covers the rest.
"""

from django.test import TestCase

from world.classes.factories import CharacterClassLevelFactory
from world.combat.consider import consider_opponent, ensure_consider_check_type
from world.combat.constants import OpponentTier, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    seed_scaling_defaults,
)
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance


class ConsiderSpendsOnceOnlyInsightTests(TestCase):
    def setUp(self) -> None:
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        CharacterClassLevelFactory(
            character=self.participant.character_sheet, level=10, is_primary=True
        )
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter, tier=OpponentTier.MOOK, level=10
        )
        self.check_type = ensure_consider_check_type()

    def _insight(self, name: str, duration: str) -> int:
        template = ConditionTemplateFactory(name=name, default_duration_type=duration)
        ConditionCheckModifierFactory(
            condition=template, check_type=self.check_type, modifier_value=3
        )
        return ConditionInstanceFactory(
            target=self.participant.character_sheet.character, condition=template
        ).pk

    def test_considering_an_enemy_spends_a_once_only_insight(self) -> None:
        pk = self._insight("Sudden Clarity 4584", DurationType.UNTIL_USED)

        consider_opponent(self.participant, self.opponent)

        self.assertFalse(ConditionInstance.objects.filter(pk=pk).exists())

    def test_considering_keeps_a_lasting_insight(self) -> None:
        pk = self._insight("Settled Clarity 4584", DurationType.ROUNDS)

        consider_opponent(self.participant, self.opponent)

        self.assertTrue(ConditionInstance.objects.filter(pk=pk).exists())
