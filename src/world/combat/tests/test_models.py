"""Tests for combat system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.combat.constants import (
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    RiskLevel,
    StakesLevel,
)
from world.combat.factories import CombatParticipantFactory
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    ThreatPool,
    ThreatPoolEntry,
)
from world.covenants.factories import CovenantRoleFactory


class CombatEncounterTests(TestCase):
    """Tests for CombatEncounter model."""

    def test_create_with_defaults(self) -> None:
        encounter = CombatEncounter.objects.create()
        self.assertEqual(encounter.encounter_type, EncounterType.PARTY_COMBAT)
        self.assertEqual(encounter.round_number, 0)
        self.assertEqual(encounter.status, EncounterStatus.BETWEEN_ROUNDS)
        self.assertEqual(encounter.risk_level, RiskLevel.MODERATE)
        self.assertEqual(encounter.stakes_level, StakesLevel.LOCAL)
        self.assertIsNone(encounter.scene)

    def test_str(self) -> None:
        encounter = CombatEncounter.objects.create(round_number=3)
        expected = "Party Combat (Round 3, Between Rounds)"
        self.assertEqual(str(encounter), expected)

    def test_str_custom_type(self) -> None:
        encounter = CombatEncounter.objects.create(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=EncounterStatus.RESOLVING,
            round_number=1,
        )
        expected = "Open Encounter (Round 1, Resolving)"
        self.assertEqual(str(encounter), expected)


class CombatOpponentTests(TestCase):
    """Tests for CombatOpponent model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounter.objects.create()

    def test_create(self) -> None:
        opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.ELITE,
            name="Shadow Knight",
            health=100,
            max_health=100,
        )
        self.assertEqual(opponent.status, OpponentStatus.ACTIVE)
        self.assertEqual(opponent.soak_value, 0)
        self.assertEqual(opponent.current_phase, 1)

    def test_str(self) -> None:
        opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            name="Dragon Lord",
            health=500,
            max_health=500,
        )
        self.assertEqual(str(opponent), "Dragon Lord (Boss)")

    def test_health_percentage_normal(self) -> None:
        opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Goblin",
            health=75,
            max_health=100,
        )
        self.assertAlmostEqual(opponent.health_percentage, 0.75)

    def test_health_percentage_negative(self) -> None:
        opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Goblin",
            health=-10,
            max_health=100,
        )
        self.assertAlmostEqual(opponent.health_percentage, 0.0)

    def test_health_percentage_zero_max(self) -> None:
        opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.SWARM,
            name="Swarm",
            health=0,
            max_health=0,
        )
        self.assertAlmostEqual(opponent.health_percentage, 0.0)


class CombatParticipantTests(TestCase):
    """Tests for CombatParticipant model."""

    def test_create_defaults(self) -> None:
        p = CombatParticipantFactory()
        assert p.encounter_id is not None
        assert p.character_sheet_id is not None
        assert p.covenant_role is None

    def test_str_with_role(self) -> None:
        role = CovenantRoleFactory(name="Sword")
        p = CombatParticipantFactory(covenant_role=role)
        assert "Sword" in str(p)

    def test_str_without_role(self) -> None:
        p = CombatParticipantFactory()
        assert str(p) == str(p.character_sheet)


class ThreatPoolTests(TestCase):
    """Tests for ThreatPool and ThreatPoolEntry models."""

    def test_pool_str(self) -> None:
        pool = ThreatPool.objects.create(name="Dragon Attacks")
        self.assertEqual(str(pool), "Dragon Attacks")

    def test_entry_str(self) -> None:
        pool = ThreatPool.objects.create(name="Dragon Attacks")
        entry = ThreatPoolEntry.objects.create(
            pool=pool,
            name="Fire Breath",
            attack_category="physical",
        )
        self.assertEqual(str(entry), "Dragon Attacks: Fire Breath")


class BossPhaseTests(TestCase):
    """Tests for BossPhase model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounter.objects.create()
        cls.opponent = CombatOpponent.objects.create(
            encounter=cls.encounter,
            tier=OpponentTier.BOSS,
            name="Dragon",
            health=500,
            max_health=500,
        )

    def test_str(self) -> None:
        phase = BossPhase.objects.create(
            opponent=self.opponent,
            phase_number=2,
        )
        self.assertEqual(str(phase), "Dragon Phase 2")

    def test_unique_constraint(self) -> None:
        BossPhase.objects.create(
            opponent=self.opponent,
            phase_number=1,
        )
        with self.assertRaises(IntegrityError):
            BossPhase.objects.create(
                opponent=self.opponent,
                phase_number=1,
            )


class FactorySmokeTest(TestCase):
    """Smoke tests verifying all combat factories create valid instances."""

    def test_encounter_factory(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        self.assertIsNotNone(encounter.pk)

    def test_opponent_factory(self) -> None:
        from world.combat.factories import CombatOpponentFactory

        opponent = CombatOpponentFactory()
        self.assertEqual(opponent.tier, OpponentTier.MOOK)

    def test_boss_factory(self) -> None:
        from world.combat.factories import BossOpponentFactory

        boss = BossOpponentFactory()
        self.assertEqual(boss.tier, OpponentTier.BOSS)
        self.assertEqual(boss.soak_value, 80)

    def test_participant_factory(self) -> None:
        from world.combat.factories import CombatParticipantFactory

        participant = CombatParticipantFactory()
        self.assertIsNotNone(participant.character_sheet)

    def test_threat_pool_entry_factory(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory()
        self.assertEqual(entry.base_damage, 10)

    def test_boss_phase_factory(self) -> None:
        from world.combat.factories import BossPhaseFactory

        phase = BossPhaseFactory()
        self.assertIsNotNone(phase.opponent)
