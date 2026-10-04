"""Force comparison and Predation."""

from unittest.mock import patch

from django.test import TestCase

from world.combat.constants import CauseKind, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.standoffs.factories import RegardRuleFactory
from world.standoffs.models import StandoffConfig
from world.standoffs.services.force import (
    cause_fires,
    effective_party_force,
    evaluate_causes,
    group_force,
    party_force,
)
from world.standoffs.services.state import is_in_standoff, open_standoff

LEVEL_PATH = "world.standoffs.services.force.effective_combat_level"


class ForceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.template = CreatureTemplateFactory(
            tier=OpponentTier.MOOK, cause=CauseKind.PREDATION, cause_margin_percent=0
        )
        cls.mooks = [
            CombatOpponentFactory(
                encounter=cls.encounter,
                creature_template=cls.template,
                tier=OpponentTier.MOOK,
                level=4,
            )
            for _ in range(4)
        ]
        cls.config = StandoffConfig.load()

    def _group(self):
        from world.standoffs.factories import StandoffGroupFactory

        return StandoffGroupFactory(encounter=self.encounter, creature_template=self.template)

    def test_group_force_uses_level_and_tier_weight(self) -> None:
        self.assertEqual(group_force(self._group(), self.config), 16)

    def test_group_force_counts_active_members_only(self) -> None:
        self.mooks[0].status = OpponentStatus.DEFEATED
        self.mooks[0].save(update_fields=["status"])
        self.assertEqual(group_force(self._group(), self.config), 12)

    def test_predation_fires_on_weak_party(self) -> None:
        with patch(LEVEL_PATH, return_value=1):
            self.assertEqual(party_force(self.encounter), 1)
            self.assertTrue(cause_fires(self._group(), self.config))

    def test_predation_does_not_fire_on_strong_party(self) -> None:
        with patch(LEVEL_PATH, return_value=20):
            self.assertFalse(cause_fires(self._group(), self.config))

    def test_cause_none_never_fires(self) -> None:
        self.template.cause = CauseKind.NONE
        self.template.save(update_fields=["cause"])
        with patch(LEVEL_PATH, return_value=1):
            self.assertFalse(cause_fires(self._group(), self.config))

    def test_emboldened_bands_tip_a_borderline_party(self) -> None:
        group = self._group()
        with patch(LEVEL_PATH, return_value=17):
            self.assertFalse(cause_fires(group, self.config))
            group.emboldened_bands = 1
            self.assertEqual(effective_party_force(self.encounter, group, self.config), 15)
            self.assertTrue(cause_fires(group, self.config))

    def test_suppressing_rule_prevents_firing(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={}, suppresses_cause=True)
        with patch(LEVEL_PATH, return_value=1):
            self.assertFalse(cause_fires(self._group(), self.config))

    def test_evaluate_causes_breaks_standoff_with_npc_initiative(self) -> None:
        with patch(LEVEL_PATH, return_value=1):
            open_standoff(self.encounter)
        self.encounter.refresh_from_db()
        self.assertFalse(is_in_standoff(self.encounter))
        self.assertEqual(self.encounter.round_number, 1)
        self.assertIs(self.encounter.initiated_by_pc_side, False)

    def test_evaluate_causes_leaves_strong_party_in_standoff(self) -> None:
        with patch(LEVEL_PATH, return_value=20):
            open_standoff(self.encounter)
            self.assertFalse(evaluate_causes(self.encounter))
        self.assertTrue(is_in_standoff(self.encounter))
