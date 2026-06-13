"""Unit tests for ``_apply_passive_technique`` (#874).

A passive IS a Technique with authored ``TechniqueAppliedCondition`` rows. The
function applies those conditions with NO dice roll (fixed scaling at
``technique.intensity`` / each row's ``minimum_success_level``) and grants
combo-opening probing to active opponents.
"""

from django.test import TestCase

from world.combat.constants import EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import _apply_passive_technique, resolve_round
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


class ResolveRoundAppliesPassiveTest(TestCase):
    """Integration: ``resolve_round`` applies declared passives this round.

    A PC declares a self-buff passive (no focused action). After ``resolve_round``
    drives the round, the passive's authored ``ConditionInstance`` must exist on
    the PC's character — proving passives land at the resolution layer, before
    focused/NPC actions resolve.

    TODO(#874 Task 9): strengthen to a damage-delta assertion (NPC attack damage
    measurably lower against a defend-archetype buff) once authored defend
    archetypes exist.
    """

    def setUp(self):
        from world.vitals.models import CharacterVitals

        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet,
            health=100,
            max_health=100,
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

        self.passive = TechniqueFactory(action_category="physical", intensity=4)
        self.applied = TechniqueAppliedConditionFactory(
            technique=self.passive,
            target_kind="self",
            base_severity=2,
            minimum_success_level=1,
        )

        CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=None,
            focused_action=None,
            physical_passive=self.passive,
        )

    def test_resolve_round_applies_declared_passive_condition(self):
        resolve_round(self.encounter)

        actor = self.participant.character_sheet.character
        instances = ConditionInstance.objects.filter(
            target=actor,
            condition=self.applied.condition,
            resolved_at__isnull=True,
        )
        self.assertTrue(
            instances.exists(),
            "resolve_round must apply the declared passive's condition to the PC.",
        )
        expected_severity = self.applied.compute_severity(
            effective_power=self.passive.intensity,
            success_level=self.applied.minimum_success_level,
        )
        self.assertEqual(instances.first().severity, expected_severity)
