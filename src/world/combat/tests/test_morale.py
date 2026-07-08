"""Tests for party-NPC morale model + state helper (#2015)."""

from django.test import TestCase

from world.combat.constants import (
    BREAK_MORALE_THRESHOLD,
    DEFAULT_OPPONENT_MORALE,
    DEMORALIZE_MORALE_PER_LEVEL,
    FALTER_MORALE_THRESHOLD,
    MINDLESS_MORALE_RESISTANCE,
    PARLEY_DISPOSITION_FLOOR,
    RALLY_BASE_DIFFICULTY,
    RALLY_MORALE_PER_LEVEL,
    TAUNT_THREAT_PER_LEVEL,
    CombatManeuver,
)
from world.combat.factories import CombatOpponentFactory, OpponentTierTemplateFactory


class MoraleConstantsTests(TestCase):
    def test_morale_threshold_constants_exist(self) -> None:
        self.assertEqual(DEFAULT_OPPONENT_MORALE, 70)
        self.assertEqual(FALTER_MORALE_THRESHOLD, 50)
        self.assertEqual(BREAK_MORALE_THRESHOLD, 25)
        self.assertEqual(DEMORALIZE_MORALE_PER_LEVEL, 15)
        self.assertEqual(RALLY_MORALE_PER_LEVEL, 15)
        self.assertEqual(TAUNT_THREAT_PER_LEVEL, 25)
        self.assertEqual(RALLY_BASE_DIFFICULTY, 10)
        self.assertEqual(PARLEY_DISPOSITION_FLOOR, 20)
        self.assertEqual(MINDLESS_MORALE_RESISTANCE, 30)

    def test_new_maneuver_enum_values(self) -> None:
        self.assertEqual(CombatManeuver.RALLY, "rally")
        self.assertEqual(CombatManeuver.DEMORALIZE, "demoralize")
        self.assertEqual(CombatManeuver.TAUNT, "taunt")
        self.assertEqual(CombatManeuver.PARLEY, "parley")


class CombatOpponentMoraleFieldTests(TestCase):
    def test_morale_defaults_to_constant(self) -> None:
        opp = CombatOpponentFactory()
        opp.refresh_from_db()
        self.assertEqual(opp.morale, DEFAULT_OPPONENT_MORALE)
        self.assertEqual(opp.max_morale, 100)

    def test_morale_can_be_overridden(self) -> None:
        opp = CombatOpponentFactory(morale=10)
        self.assertEqual(opp.morale, 10)


class OpponentTierTemplateHasMoraleTests(TestCase):
    def test_has_morale_defaults_true(self) -> None:
        tpl = OpponentTierTemplateFactory()
        self.assertTrue(tpl.has_morale)


class ThreatPoolEntryRequiresSteadyTests(TestCase):
    def test_requires_steady_defaults_false(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory()
        self.assertFalse(entry.requires_steady)


# ---------------------------------------------------------------------------
# Task 2: morale state helper + mutation service
# ---------------------------------------------------------------------------

from world.combat.morale import (  # noqa: E402
    OpponentMoraleState,
    apply_morale_damage,
    morale_state_for,
    tier_has_morale,
)


class MoraleStateForTests(TestCase):
    def test_steady_above_falter_threshold(self) -> None:
        opp = CombatOpponentFactory(morale=80)
        self.assertEqual(morale_state_for(opp), OpponentMoraleState.STEADY)

    def test_falter_at_threshold(self) -> None:
        opp = CombatOpponentFactory(morale=FALTER_MORALE_THRESHOLD)
        self.assertEqual(morale_state_for(opp), OpponentMoraleState.FALTER)

    def test_break_at_threshold(self) -> None:
        opp = CombatOpponentFactory(morale=BREAK_MORALE_THRESHOLD)
        self.assertEqual(morale_state_for(opp), OpponentMoraleState.BREAK)

    def test_break_reads_raw_morale_regardless_of_mindless(self) -> None:
        """A mindless opponent driven low by a breakthrough still breaks."""
        tpl = OpponentTierTemplateFactory(has_morale=False)
        opp = CombatOpponentFactory(tier=tpl.tier, morale=BREAK_MORALE_THRESHOLD)
        self.assertEqual(morale_state_for(opp), OpponentMoraleState.BREAK)


class TierHasMoraleTests(TestCase):
    def test_default_tier_has_morale(self) -> None:
        opp = CombatOpponentFactory()
        self.assertTrue(tier_has_morale(opp))

    def test_mindless_tier_has_no_morale(self) -> None:
        tpl = OpponentTierTemplateFactory(has_morale=False)
        opp = CombatOpponentFactory(tier=tpl.tier)
        self.assertFalse(tier_has_morale(opp))


class ApplyMoraleDamageTests(TestCase):
    def test_depletes_morale(self) -> None:
        opp = CombatOpponentFactory(morale=70)
        applied = apply_morale_damage(opp, 15)
        self.assertEqual(applied, 15)
        opp.refresh_from_db()
        self.assertEqual(opp.morale, 55)

    def test_clamps_at_zero(self) -> None:
        opp = CombatOpponentFactory(morale=5)
        applied = apply_morale_damage(opp, 100)
        self.assertEqual(applied, 5)
        opp.refresh_from_db()
        self.assertEqual(opp.morale, 0)

    def test_swarm_clears_bodies_on_morale_loss(self) -> None:
        from world.combat.constants import OpponentTier

        OpponentTierTemplateFactory(tier=OpponentTier.SWARM)
        opp = CombatOpponentFactory(
            tier=OpponentTier.SWARM,
            swarm_count=20,
            max_swarm_count=20,
            body_toughness=5,
            morale=70,
        )
        apply_morale_damage(opp, 15)  # 15 // 5 = 3 bodies flee
        opp.refresh_from_db()
        self.assertEqual(opp.swarm_count, 17)

    def test_non_swarm_ignores_body_clearing(self) -> None:
        opp = CombatOpponentFactory(morale=70)  # MOOK by default
        apply_morale_damage(opp, 15)
        opp.refresh_from_db()
        self.assertEqual(opp.morale, 55)
