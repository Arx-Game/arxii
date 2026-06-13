"""Hero Killer tier (#875): unbeatable, victory-blocked, escape-only."""

from django.test import TestCase

from world.combat.constants import EncounterOutcome, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    HeroKillerOpponentFactory,
)
from world.combat.services import _classify_encounter_outcome, apply_damage_to_opponent


class HeroKillerDamageTests(TestCase):
    def test_damage_never_defeats_hero_killer(self):
        hk = HeroKillerOpponentFactory(health=10, max_health=9999, soak_value=0)
        result = apply_damage_to_opponent(hk, 1_000_000)
        hk.refresh_from_db()
        self.assertFalse(result.defeated)
        self.assertEqual(hk.status, OpponentStatus.ACTIVE)


class HeroKillerOutcomeTests(TestCase):
    def test_victory_blocked_while_hero_killer_present(self):
        encounter = CombatEncounterFactory()
        # Even an (artificially) non-active Hero Killer blocks victory: the
        # fight was never winnable.
        HeroKillerOpponentFactory(encounter=encounter, status=OpponentStatus.DEFEATED)
        self.assertNotEqual(_classify_encounter_outcome(encounter), EncounterOutcome.VICTORY)


class ForcedEscapeFlagTests(TestCase):
    def test_forced_escape_true_with_active_hero_killer(self):
        encounter = CombatEncounterFactory()
        hk = HeroKillerOpponentFactory(encounter=encounter)
        self.assertTrue(encounter.forced_escape)
        hk.status = OpponentStatus.FLED  # no longer on the field
        hk.save(update_fields=["status"])
        self.assertFalse(encounter.forced_escape)


class HeroKillerEscapeArcTests(TestCase):
    """End-to-end escape arc: Hero Killer survives all damage; all-fled PCs → FLED (#875)."""

    def test_all_pcs_flee_yields_fled_not_victory(self):
        encounter = CombatEncounterFactory()
        HeroKillerOpponentFactory(encounter=encounter)
        CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.FLED)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.FLED)
        self.assertTrue(encounter.forced_escape)
