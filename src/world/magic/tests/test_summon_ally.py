"""Tests for the summon_ally cast-time effect handler (#1584).

SQLite-safe: add_opponent is called with explicit max_health (manual mode) so
the scaling formula (compute_opponent_stat_block) never runs.  All DB setup uses
FactoryBoy factories.

Two cases:
  1. Happy path: caster is in an active encounter → a new ALLY CombatOpponent is
     created with the correct fields and is hostile to existing ENEMY opponents.
  2. No-op path: caster is NOT in any active encounter → summon_ally returns early;
     no CombatOpponent is created.
"""

from types import SimpleNamespace

from django.test import TestCase

from world.combat.constants import CombatAllegiance, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import combatants_hostile_to
from world.magic.services.effect_handlers import summon_ally


class SummonAllyHandlerTests(TestCase):
    """summon_ally creates an ALLY CombatOpponent in the caster's encounter."""

    def test_happy_path_creates_ally_opponent(self) -> None:
        """Caster in active encounter → ALLY opponent with correct fields is created."""
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)

        # An existing ENEMY in the same encounter — used to verify hostility later.
        enemy = CombatOpponentFactory(encounter=encounter)

        # Caster participant in the same encounter.
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        caster_objectdb = participant.character_sheet.character

        payload = SimpleNamespace(
            caster=caster_objectdb,
            threat_pool_name=pool.name,
            bond_rounds=5,
        )

        before_count = CombatOpponent.objects.filter(encounter=encounter).count()

        summon_ally(payload=payload)

        # Exactly one new CombatOpponent was added.
        after_count = CombatOpponent.objects.filter(encounter=encounter).count()
        self.assertEqual(after_count, before_count + 1)

        # Retrieve the summon (it's the one with allegiance=ALLY).
        summon = CombatOpponent.objects.get(encounter=encounter, allegiance=CombatAllegiance.ALLY)

        # Allegiance is ALLY.
        self.assertEqual(summon.allegiance, CombatAllegiance.ALLY)

        # summoned_by is the caster's CharacterSheet.
        self.assertEqual(summon.summoned_by, participant.character_sheet)

        # Ephemeral objectdb (no persona, no pre-existing OD supplied).
        self.assertTrue(summon.objectdb_is_ephemeral)

        # bond_expires_round = encounter.round_number (0 by default) + 5.
        self.assertEqual(summon.bond_expires_round, encounter.round_number + 5)

        # threat_pool is the pool we supplied.
        self.assertEqual(summon.threat_pool_id, pool.pk)

        # The summon is hostile to the ENEMY opponent (via combatants_hostile_to).
        hostile = combatants_hostile_to(summon)
        self.assertIn(enemy, hostile["opponents"])

        # The summon is NOT hostile to PC participants.
        self.assertEqual(hostile["participants"], [])

    def test_no_op_when_caster_not_in_combat(self) -> None:
        """Caster with no active CombatParticipant → returns early; no opponent created."""
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)

        # Create a participant in a separate encounter so the DB is not empty —
        # ensures the filter genuinely misses the caster, not a blanket-empty check.
        other_participant = CombatParticipantFactory(status=ParticipantStatus.ACTIVE)

        # A character NOT in any encounter.
        from evennia_extensions.factories import CharacterFactory

        unrelated_caster = CharacterFactory()

        initial_count = CombatOpponent.objects.count()

        payload = SimpleNamespace(
            caster=unrelated_caster,
            threat_pool_name=pool.name,
            bond_rounds=5,
        )

        result = summon_ally(payload=payload)

        # Handler returned (None is fine; no exception).
        self.assertIsNone(result)

        # No new opponent was created.
        self.assertEqual(CombatOpponent.objects.count(), initial_count)

        # Sanity: the other encounter's participant is untouched.
        other_participant.refresh_from_db()
        self.assertEqual(other_participant.status, ParticipantStatus.ACTIVE)


class SummonAllyMilitaryBranchTests(TestCase):
    """military=True routes to a BattleUnit instead of a CombatOpponent (#1711)."""

    def test_military_summon_creates_battle_unit_not_combat_opponent(self) -> None:
        from world.battles.constants import BattleSideRole
        from world.battles.models import BattleUnit
        from world.battles.services import add_side, create_battle, enlist_participant
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import CapabilityTypeFactory
        from world.mechanics.factories import PropertyFactory

        battle = create_battle(name="Military Summon Test Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        sheet = CharacterSheetFactory()
        enlist_participant(battle=battle, character_sheet=sheet, side=side)

        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)

        flying = PropertyFactory(name="flying")
        flight_cap = CapabilityTypeFactory(name="flight")

        payload = SimpleNamespace(
            caster=sheet.character,
            threat_pool_name=pool.name,
            military=True,
            max_health=200,
            properties=["flying"],
            capabilities={"flight": 30},
        )

        before_units = BattleUnit.objects.filter(battle=battle).count()
        before_opponents = CombatOpponent.objects.count()

        summon_ally(payload=payload)

        after_units = BattleUnit.objects.filter(battle=battle).count()
        after_opponents = CombatOpponent.objects.count()

        self.assertEqual(after_units, before_units + 1)
        self.assertEqual(after_opponents, before_opponents)

        unit = BattleUnit.objects.filter(battle=battle).latest("pk")
        self.assertEqual(unit.side, side)
        self.assertEqual(unit.strength, 200)
        self.assertTrue(unit.has_property(flying))
        self.assertEqual(unit.effective_capability(flight_cap), 30)
        self.assertEqual(unit.summoned_by, sheet)

    def test_military_summon_no_op_without_active_battle_participant(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.battles.models import BattleUnit

        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        caster = CharacterFactory()

        payload = SimpleNamespace(caster=caster, threat_pool_name=pool.name, military=True)

        before = BattleUnit.objects.count()
        result = summon_ally(payload=payload)
        self.assertIsNone(result)
        self.assertEqual(BattleUnit.objects.count(), before)

    def test_non_military_skirmish_path_unaffected(self) -> None:
        """Regression: military absent/False keeps the pre-#1711 behavior byte-identical."""
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        caster_objectdb = participant.character_sheet.character

        payload = SimpleNamespace(caster=caster_objectdb, threat_pool_name=pool.name)

        before = CombatOpponent.objects.filter(encounter=encounter).count()
        summon_ally(payload=payload)
        after = CombatOpponent.objects.filter(encounter=encounter).count()
        self.assertEqual(after, before + 1)
