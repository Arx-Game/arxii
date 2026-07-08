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
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)


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


# ---------------------------------------------------------------------------
# Task 3: falter/break wiring in select_npc_actions
# ---------------------------------------------------------------------------

from world.combat.constants import (  # noqa: E402
    OpponentStatus,
)
from world.combat.services import select_npc_actions  # noqa: E402
from world.scenes.constants import RoundStatus  # noqa: E402
from world.vitals.models import CharacterVitals  # noqa: E402


class SelectNpcActionsMoraleTests(TestCase):
    """Morale-state-driven NPC behavior in select_npc_actions (#2015)."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(round_number=1, status=RoundStatus.DECLARING)
        self.pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(
            pool=self.pool,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.RANDOM,
        )
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.create(
            character_sheet=self.participant.character_sheet,
            health=100,
            max_health=100,
        )

    def test_broken_opponent_flees_and_skips_round(self) -> None:
        opp = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.pool,
            morale=BREAK_MORALE_THRESHOLD,
        )
        actions = select_npc_actions(self.encounter)
        self.assertEqual(actions, [])
        opp.refresh_from_db()
        self.assertEqual(opp.status, OpponentStatus.FLED)

    def test_faltering_opponent_skips_requires_steady_entries(self) -> None:
        # Two entries: one requires_steady (skipped when faltering), one normal.
        # The setUp self.entry also exists (non-steady); assert the steady one
        # is never selected when faltering, despite its high weight.
        ThreatPoolEntryFactory(pool=self.pool, requires_steady=True, weight=1000)
        CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=self.pool,
            morale=FALTER_MORALE_THRESHOLD,
        )
        actions = select_npc_actions(self.encounter)
        self.assertEqual(len(actions), 1)
        # The requires_steady entry must NOT have been selected despite weight=1000.
        self.assertFalse(actions[0].threat_entry.requires_steady)
