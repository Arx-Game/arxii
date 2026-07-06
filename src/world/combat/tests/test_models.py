"""Tests for combat system models."""

from django.db import IntegrityError
from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.combat.constants import (
    ActionCategory,
    EncounterType,
    OpponentStatus,
    OpponentTier,
    RiskLevel,
    StakesLevel,
)
from world.combat.factories import CombatParticipantFactory
from world.combat.models import (
    BossPhase,
    CombatOpponent,
    ThreatPool,
    ThreatPoolEntry,
)
from world.covenants.factories import CovenantRoleFactory
from world.scenes.constants import RoundStatus


class CombatEncounterTests(TestCase):
    """Tests for CombatEncounter model."""

    def test_create_with_defaults(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory()
        self.assertEqual(encounter.encounter_type, EncounterType.PARTY_COMBAT)
        self.assertEqual(encounter.round_number, 0)
        self.assertEqual(encounter.status, RoundStatus.BETWEEN_ROUNDS)
        self.assertEqual(encounter.risk_level, RiskLevel.MODERATE)
        self.assertEqual(encounter.stakes_level, StakesLevel.LOCAL)
        self.assertIsNotNone(encounter.scene)

    def test_str(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory(round_number=3)
        expected = "Party Combat (Round 3, Between Rounds)"
        self.assertEqual(str(encounter), expected)

    def test_str_custom_type(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        encounter = CombatEncounterFactory(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=RoundStatus.RESOLVING,
            round_number=1,
        )
        expected = "Open Encounter (Round 1, Resolving)"
        self.assertEqual(str(encounter), expected)

    def test_scene_protected_from_delete(self) -> None:
        from django.db.models import ProtectedError

        from world.combat.factories import CombatEncounterFactory

        enc = CombatEncounterFactory()
        with self.assertRaises(ProtectedError):
            enc.scene.delete()


class CombatOpponentTests(TestCase):
    """Tests for CombatOpponent model."""

    def setUp(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        self.encounter = CombatEncounterFactory()

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

    def setUp(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
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


class ThreatPoolEntryDefenseCheckTypeTest(TestCase):
    """Tests for the defense_check_type FK on ThreatPoolEntry (#1994)."""

    def test_defense_check_type_nullable(self) -> None:
        """ThreatPoolEntry.defense_check_type is nullable (backward-compatible)."""
        from world.combat.models import ThreatPool, ThreatPoolEntry

        pool = ThreatPool.objects.create(name="test-pool")
        entry = ThreatPoolEntry.objects.create(
            pool=pool,
            name="test-entry",
            attack_category=ActionCategory.PHYSICAL,
        )
        self.assertIsNone(entry.defense_check_type)

    def test_defense_check_type_set_null_on_delete(self) -> None:
        """Deleting a CheckType sets threat entries to null (SET_NULL).

        Uses ``values()`` to bypass the SharedMemoryModel identity map, which
        caches the FK reference and does not reflect the null after delete.
        """
        from world.checks.models import CheckCategory, CheckType
        from world.combat.models import ThreatPool, ThreatPoolEntry

        pool = ThreatPool.objects.create(name="test-pool-2")
        category = CheckCategory.objects.create(name="test-category")
        ct = CheckType.objects.create(name="test-defense", category=category)
        entry = ThreatPoolEntry.objects.create(
            pool=pool,
            name="test-entry-2",
            attack_category=ActionCategory.PHYSICAL,
            defense_check_type=ct,
        )
        ct.delete()
        # Bypass the identity map — read the raw DB column value.
        raw = ThreatPoolEntry.objects.filter(pk=entry.pk).values("defense_check_type_id").first()
        self.assertIsNone(raw["defense_check_type_id"])


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


class ThreatPoolEntryDamageTypeTests(EvenniaTestCase):
    """Tests for ThreatPoolEntry.damage_type FK."""

    def test_threat_pool_entry_can_have_damage_type(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory
        from world.conditions.factories import DamageTypeFactory

        fire = DamageTypeFactory(name="Fire")
        entry = ThreatPoolEntryFactory(damage_type=fire)
        self.assertEqual(entry.damage_type, fire)

    def test_threat_pool_entry_damage_type_nullable(self) -> None:
        from world.combat.factories import ThreatPoolEntryFactory

        entry = ThreatPoolEntryFactory(damage_type=None)
        self.assertIsNone(entry.damage_type)


class CombatManeuverFieldTests(TestCase):
    """Tests for CombatRoundAction.maneuver field (#878)."""

    def test_maneuver_defaults_null(self) -> None:
        """maneuver is null for a normal (non-maneuver) declaration."""
        from world.combat.factories import CombatRoundActionFactory

        action = CombatRoundActionFactory()
        self.assertIsNone(action.maneuver)

    def test_maneuver_accepts_flee(self) -> None:
        """maneuver field accepts CombatManeuver.FLEE."""
        from world.combat.constants import CombatManeuver
        from world.combat.factories import CombatParticipantFactory, CombatRoundActionFactory

        participant = CombatParticipantFactory()
        action = CombatRoundActionFactory(
            participant=participant,
            round_number=99,
            maneuver=CombatManeuver.FLEE,
        )
        action.refresh_from_db()
        self.assertEqual(action.maneuver, CombatManeuver.FLEE)

    def test_maneuver_accepts_cover(self) -> None:
        """maneuver field accepts CombatManeuver.COVER."""
        from world.combat.constants import CombatManeuver
        from world.combat.factories import CombatParticipantFactory, CombatRoundActionFactory

        participant = CombatParticipantFactory()
        action = CombatRoundActionFactory(
            participant=participant,
            round_number=98,
            maneuver=CombatManeuver.COVER,
        )
        action.refresh_from_db()
        self.assertEqual(action.maneuver, CombatManeuver.COVER)


class FleeTierModifierTests(TestCase):
    """Tests for FleeTierModifier model (#878)."""

    def test_tier_uniqueness_enforced(self) -> None:
        """Two FleeTierModifier rows with the same tier raise IntegrityError."""
        from world.combat.models import FleeTierModifier

        FleeTierModifier.objects.create(tier=OpponentTier.MOOK, difficulty_modifier=5)
        with self.assertRaises(IntegrityError):
            FleeTierModifier.objects.create(tier=OpponentTier.MOOK, difficulty_modifier=10)

    def test_str(self) -> None:
        """__str__ includes tier and sign-formatted modifier."""
        from world.combat.models import FleeTierModifier

        modifier = FleeTierModifier(tier=OpponentTier.BOSS, difficulty_modifier=8)
        self.assertEqual(str(modifier), "FleeTierModifier(boss: +8)")

    def test_negative_modifier_str(self) -> None:
        """__str__ correctly formats negative modifiers."""
        from world.combat.models import FleeTierModifier

        modifier = FleeTierModifier(tier=OpponentTier.SWARM, difficulty_modifier=-3)
        self.assertEqual(str(modifier), "FleeTierModifier(swarm: -3)")


class FleeConfigTests(TestCase):
    """Tests for FleeConfig model (#878)."""

    def test_str(self) -> None:
        """__str__ includes pk."""
        from world.combat.models import FleeConfig

        config = FleeConfig(pk=1)
        self.assertEqual(str(config), "FleeConfig(pk=1)")


class CombatParticipantCurrentPositionTests(EvenniaTestCase):
    """Tests for CombatParticipant.current_position derived property (#530)."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.factories import PositionFactory
        from world.areas.positioning.models import Position
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory

        # Create a room and position in the same room.
        self.room = create_object("typeclasses.rooms.Room", key="Position Test Room", nohome=True)
        self.position: Position = PositionFactory(room=self.room, name="test_pos")

        # Build a participant whose character is located in that room.
        from world.character_sheets.factories import CharacterSheetFactory

        self.sheet = CharacterSheetFactory()
        # Move the character into the room so place_in_position doesn't raise.
        self.sheet.character.location = self.room
        self.sheet.character.save()

        encounter = CombatEncounterFactory(room=self.room)
        self.participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)

    def test_current_position_when_placed(self) -> None:
        """Returns the Position when the character occupies one."""
        from world.areas.positioning.services import place_in_position

        place_in_position(self.sheet.character, self.position)
        # Fresh instance (cached_property must not be inherited from setUp instance).
        from world.combat.models import CombatParticipant

        fresh = CombatParticipant.objects.get(pk=self.participant.pk)
        self.assertEqual(fresh.current_position, self.position)

    def test_current_position_when_unplaced(self) -> None:
        """Returns None when the character has no ObjectPosition row."""
        from world.combat.models import CombatParticipant

        fresh = CombatParticipant.objects.get(pk=self.participant.pk)
        self.assertIsNone(fresh.current_position)


class CombatOpponentCurrentPositionTests(EvenniaTestCase):
    """Tests for CombatOpponent.current_position derived property (#530)."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.factories import PositionFactory
        from world.areas.positioning.models import Position
        from world.combat.factories import CombatEncounterFactory
        from world.combat.models import CombatOpponent
        from world.combat.typeclasses.combat_npc import CombatNPC

        # Create a room and position in the same room.
        self.room = create_object("typeclasses.rooms.Room", key="Opp Position Room", nohome=True)
        self.position: Position = PositionFactory(room=self.room, name="opp_pos")

        # Build an encounter and an NPC opponent in that room.
        self.encounter = CombatEncounterFactory(room=self.room)
        self.npc = create_object(CombatNPC, key="Test NPC", location=self.room, nohome=True)
        self.opponent = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Test Mook",
            health=50,
            max_health=50,
            objectdb=self.npc,
            objectdb_is_ephemeral=True,
        )

    def test_current_position_when_placed(self) -> None:
        """Returns the Position when the NPC's ObjectDB occupies one."""
        from world.areas.positioning.services import place_in_position
        from world.combat.models import CombatOpponent

        place_in_position(self.npc, self.position)
        fresh = CombatOpponent.objects.get(pk=self.opponent.pk)
        self.assertEqual(fresh.current_position, self.position)

    def test_current_position_when_unplaced(self) -> None:
        """Returns None when the NPC has no ObjectPosition row."""
        from world.combat.models import CombatOpponent

        fresh = CombatOpponent.objects.get(pk=self.opponent.pk)
        self.assertIsNone(fresh.current_position)

    def test_current_position_when_objectdb_null(self) -> None:
        """Returns None when objectdb FK is null (externally destroyed NPC)."""
        from world.combat.models import CombatOpponent

        # Create an opponent with no objectdb (non-ephemeral to satisfy clean()).
        opponent_no_obj = CombatOpponent.objects.create(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Ghostly Mook",
            health=10,
            max_health=10,
            objectdb=None,
            objectdb_is_ephemeral=False,
        )
        self.assertIsNone(opponent_no_obj.current_position)


class CombatRoundActionCommitmentTests(TestCase):
    """Tests that CombatRoundAction carries commitment and soulfray-accept fields."""

    def test_combat_round_action_carries_commitment_fields(self) -> None:
        from world.combat.factories import CombatRoundActionFactory

        action = CombatRoundActionFactory()
        self.assertFalse(action.confirm_soulfray_risk)
        self.assertIsNone(action.fury_commitment)
        self.assertIsNone(action.fury_anchor)
        self.assertEqual(action.strain_commitment, 0)
