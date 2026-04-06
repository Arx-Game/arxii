"""Tests for combat system models."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    COVENANT_ROLE_SPEED_RANK,
    NO_ROLE_SPEED_RANK,
    CovenantRole,
    EncounterStatus,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    ThreatPool,
    ThreatPoolEntry,
)


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
        self.assertIsNone(encounter.story)
        self.assertIsNone(encounter.episode)

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

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounter.objects.create()
        cls.sheet = CharacterSheetFactory()

    def _make_participant(self, **kwargs: object) -> CombatParticipant:
        defaults = {
            "encounter": self.encounter,
            "character_sheet": self.sheet,
            "health": 100,
            "max_health": 100,
        }
        defaults.update(kwargs)
        return CombatParticipant.objects.create(**defaults)

    def test_create_defaults(self) -> None:
        p = self._make_participant()
        self.assertEqual(p.status, ParticipantStatus.ACTIVE)
        self.assertIsNone(p.covenant_role)
        self.assertEqual(p.speed_modifier, 0)
        self.assertFalse(p.dying_final_round)

    def test_str_with_role(self) -> None:
        p = self._make_participant(covenant_role=CovenantRole.VANGUARD)
        self.assertIn("Vanguard", str(p))

    def test_str_without_role(self) -> None:
        p = self._make_participant()
        self.assertEqual(str(p), str(self.sheet))

    def test_effective_speed_rank_no_role(self) -> None:
        p = self._make_participant()
        self.assertEqual(p.effective_speed_rank, NO_ROLE_SPEED_RANK)

    def test_effective_speed_rank_with_role(self) -> None:
        for role, expected_rank in COVENANT_ROLE_SPEED_RANK.items():
            p = self._make_participant(covenant_role=role)
            self.assertEqual(
                p.effective_speed_rank,
                expected_rank,
                msg=f"Role {role} should have speed rank {expected_rank}",
            )

    def test_effective_speed_rank_with_modifier(self) -> None:
        p = self._make_participant(
            covenant_role=CovenantRole.VANGUARD,
            speed_modifier=-2,
        )
        # Vanguard base is 1, minus 2 = -1, clamped to 1
        self.assertEqual(p.effective_speed_rank, 1)

    def test_effective_speed_rank_positive_modifier(self) -> None:
        p = self._make_participant(
            covenant_role=CovenantRole.VANGUARD,
            speed_modifier=3,
        )
        # Vanguard base is 1, plus 3 = 4
        self.assertEqual(p.effective_speed_rank, 4)

    def test_health_percentage_normal(self) -> None:
        p = self._make_participant(health=50, max_health=100)
        self.assertAlmostEqual(p.health_percentage, 0.5)

    def test_health_percentage_negative(self) -> None:
        p = self._make_participant(health=-20, max_health=100)
        self.assertAlmostEqual(p.health_percentage, 0.0)

    def test_health_percentage_zero_max(self) -> None:
        p = self._make_participant(health=0, max_health=0)
        self.assertAlmostEqual(p.health_percentage, 0.0)

    def test_wound_description_full_health(self) -> None:
        p = self._make_participant(health=100, max_health=100)
        self.assertEqual(p.wound_description, "barely scratched")

    def test_wound_description_half_health(self) -> None:
        p = self._make_participant(health=50, max_health=100)
        self.assertEqual(p.wound_description, "seriously wounded")

    def test_wound_description_low_health(self) -> None:
        p = self._make_participant(health=25, max_health=100)
        self.assertEqual(p.wound_description, "near collapse")

    def test_wound_description_zero_health(self) -> None:
        p = self._make_participant(health=0, max_health=100)
        self.assertEqual(p.wound_description, "incapacitated")

    def test_wound_description_negative_health(self) -> None:
        p = self._make_participant(health=-10, max_health=100)
        self.assertEqual(p.wound_description, "incapacitated")


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
