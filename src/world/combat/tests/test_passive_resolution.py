"""Unit tests for ``_apply_passive_technique`` (#874).

A passive IS a Technique with authored ``TechniqueAppliedCondition`` rows. The
function applies those conditions with NO dice roll (fixed scaling at
``technique.intensity`` / each row's ``minimum_success_level``) and grants
combo-opening probing to active opponents.
"""

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import _apply_passive_technique
from world.conditions.models import ConditionInstance
from world.magic.factories import TechniqueAppliedConditionFactory, TechniqueFactory


class ApplyPassiveTechniqueSelfBuffTest(TestCase):
    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.tech = TechniqueFactory(action_category="physical", intensity=4)
        self.applied = TechniqueAppliedConditionFactory(
            technique=self.tech,
            target_kind="self",
            base_severity=2,
            minimum_success_level=1,
        )

    def test_applies_self_condition_to_actor(self):
        _apply_passive_technique(self.tech, self.participant, self.encounter)

        actor = self.participant.character_sheet.character
        instances = ConditionInstance.objects.filter(
            target=actor,
            condition=self.applied.condition,
            resolved_at__isnull=True,
        )
        self.assertTrue(instances.exists())
        # No-roll scaling: severity == compute_severity at intensity / min SL.
        expected_severity = self.applied.compute_severity(
            effective_power=self.tech.intensity,
            success_level=self.applied.minimum_success_level,
        )
        self.assertEqual(instances.first().severity, expected_severity)


class ApplyPassiveTechniqueComboOpeningTest(TestCase):
    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.tech = TechniqueFactory(
            action_category="physical",
            intensity=4,
            combo_opening_probing=3,
        )

    def test_grants_probing_to_active_opponent(self):
        before = self.opponent.probing_current
        _apply_passive_technique(self.tech, self.participant, self.encounter)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.probing_current, before + 3)
