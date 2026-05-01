"""Tests for combat system models."""

from django.db import IntegrityError
from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.combat.constants import (
    ActionCategory,
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

    def test_persona_nullable(self) -> None:
        from world.combat.factories import CombatOpponentFactory

        opp = CombatOpponentFactory()
        assert opp.persona is None

    def test_persona_linkage(self) -> None:
        from world.combat.factories import CombatOpponentFactory
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        opp = CombatOpponentFactory(persona=persona)
        assert opp.persona == persona


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
            attack_category=ActionCategory.PHYSICAL,
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


class CombatTechniqueIntegrationTests(TestCase):
    """Smoke tests for combat-magic pipeline dataclasses."""

    def test_combat_technique_resolution_importable(self) -> None:
        """Smoke test: CombatTechniqueResolution importable and constructible."""
        from unittest.mock import MagicMock

        from world.checks.types import CheckResult
        from world.combat.types import CombatTechniqueResolution

        res = CombatTechniqueResolution(
            check_result=MagicMock(spec=CheckResult),
            damage_results=[],
            applied_conditions=[],
            pull_flat_bonus=0,
            scaled_damage=0,
        )
        self.assertEqual(res.scaled_damage, 0)

    def test_combat_technique_result_importable(self) -> None:
        """Smoke test: CombatTechniqueResult importable and constructible."""
        from unittest.mock import MagicMock

        from world.combat.types import CombatTechniqueResult
        from world.magic.types import TechniqueUseResult

        res = CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=MagicMock(spec=TechniqueUseResult),
        )
        self.assertEqual(res.damage_results, [])


class CombatEncounterRoomTests(EvenniaTestCase):
    def test_encounter_has_room_fk(self) -> None:
        from evennia import create_object

        from world.combat.factories import CombatEncounterFactory

        room = create_object("typeclasses.rooms.Room", key="Combat Room", nohome=True)
        enc = CombatEncounterFactory(room=room)
        self.assertEqual(enc.room, room)


class CombatOpponentSchemaConstraintTests(EvenniaTestCase):
    def test_persona_bearing_opponent_cannot_be_ephemeral_db_layer(self) -> None:
        from django.db import IntegrityError, transaction

        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.models import CombatOpponent
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        encounter = CombatEncounterFactory()
        threat_pool = ThreatPoolFactory()
        objdb = persona.character_sheet.character
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CombatOpponent.objects.create(
                    encounter=encounter,
                    name="Bad Mook",
                    tier="minor",
                    max_health=10,
                    health=10,
                    threat_pool=threat_pool,
                    persona=persona,
                    objectdb=objdb,
                    objectdb_is_ephemeral=True,  # violates check
                )


class CombatOpponentCleanTests(EvenniaTestCase):
    """Layer 2 multi-validation guards on CombatOpponent."""

    def test_clean_rejects_ephemeral_with_no_objectdb(self):
        from django.core.exceptions import ValidationError

        from world.combat.factories import CombatOpponentFactory

        # objectdb_id=None suppresses the factory's lazy_attribute so we can
        # test clean() with a genuinely null ObjectDB reference.
        opp = CombatOpponentFactory.build(
            objectdb=None, objectdb_id=None, objectdb_is_ephemeral=True
        )
        with self.assertRaises(ValidationError):
            opp.clean()

    def test_clean_rejects_ephemeral_with_persona(self):
        from django.core.exceptions import ValidationError
        from evennia import create_object

        from world.combat.factories import CombatOpponentFactory
        from world.combat.typeclasses.combat_npc import CombatNPC
        from world.scenes.factories import PersonaFactory

        npc = create_object(CombatNPC, key="Conflicted", nohome=True)
        persona = PersonaFactory()
        # objectdb_id=npc.pk ensures the factory uses the given NPC, not a new one.
        opp = CombatOpponentFactory.build(
            persona=persona,
            objectdb=npc,
            objectdb_id=npc.pk,
            objectdb_is_ephemeral=True,
        )
        with self.assertRaises(ValidationError):
            opp.clean()

    def test_clean_rejects_ephemeral_non_combat_npc_typeclass(self):
        from django.core.exceptions import ValidationError
        from evennia import create_object

        from world.combat.factories import CombatOpponentFactory

        regular_char = create_object("typeclasses.characters.Character", key="NotANPC", nohome=True)
        # objectdb_id=regular_char.pk ensures the factory uses the given char, not a new CombatNPC.
        opp = CombatOpponentFactory.build(
            objectdb=regular_char,
            objectdb_id=regular_char.pk,
            objectdb_is_ephemeral=True,
        )
        with self.assertRaises(ValidationError):
            opp.clean()

    def test_clean_rejects_ephemeral_with_persistent_references(self):
        from django.core.exceptions import ValidationError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import CombatOpponentFactory

        sheet = CharacterSheetFactory()
        # objectdb_id=sheet.character.pk ensures the factory uses the given char,
        # not a new CombatNPC from the lazy_attribute.
        opp = CombatOpponentFactory.build(
            objectdb=sheet.character,
            objectdb_id=sheet.character.pk,
            objectdb_is_ephemeral=True,
        )
        with self.assertRaises(ValidationError):
            opp.clean()

    def test_clean_passes_for_non_ephemeral_persona_bearing(self):
        # Sanity: non-ephemeral with persona is allowed
        from world.combat.factories import CombatOpponentFactory
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        char = persona.character_sheet.character
        # objectdb_id=char.pk ensures the factory uses the persona's char, not a new CombatNPC.
        opp = CombatOpponentFactory.build(
            persona=persona,
            objectdb=char,
            objectdb_id=char.pk,
            objectdb_is_ephemeral=False,
        )
        opp.clean()  # should not raise


class CombatRoundActionAllyTargetTests(EvenniaTestCase):
    """Tests for ally targeting on CombatRoundAction."""

    def test_action_can_have_ally_target(self) -> None:
        from world.combat.factories import CombatParticipantFactory, CombatRoundActionFactory

        ally = CombatParticipantFactory()
        action = CombatRoundActionFactory(focused_ally_target=ally)
        self.assertEqual(action.focused_ally_target, ally)

    def test_xor_target_validation(self) -> None:
        from django.core.exceptions import ValidationError

        from world.combat.factories import (
            CombatOpponentFactory,
            CombatParticipantFactory,
            CombatRoundActionFactory,
        )

        ally = CombatParticipantFactory()
        opp = CombatOpponentFactory()
        action = CombatRoundActionFactory.build(
            focused_ally_target=ally,
            focused_opponent_target=opp,
        )
        with self.assertRaises(ValidationError):
            action.full_clean()
