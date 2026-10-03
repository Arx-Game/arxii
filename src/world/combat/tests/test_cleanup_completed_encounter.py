"""Tests for cleanup_completed_encounter — Layer 5 of the multi-layer identity guard."""

from unittest import mock

from django.test import TestCase
from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase


class CleanupCompletedEncounterTests(EvenniaTestCase):
    def test_cleanup_deletes_ephemeral_only(self):
        from evennia.objects.models import ObjectDB

        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent, cleanup_completed_encounter
        from world.scenes.factories import PersonaFactory

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        mook = add_opponent(encounter, name="Mook", tier="mook", max_health=10, threat_pool=pool)
        persona = PersonaFactory()
        named = add_opponent(
            encounter, name="Boss", tier="boss", max_health=100, threat_pool=pool, persona=persona
        )
        existing = create_object("typeclasses.characters.Character", key="Survivor", nohome=True)
        pvp = add_opponent(
            encounter,
            name="PvP",
            tier="elite",
            max_health=80,
            threat_pool=pool,
            existing_objectdb=existing,
        )

        mook_od_pk = mook.objectdb_id
        named_od_pk = named.objectdb_id
        pvp_od_pk = pvp.objectdb_id

        cleanup_completed_encounter(encounter)

        # mook ObjectDB gone
        self.assertFalse(ObjectDB.objects.filter(pk=mook_od_pk).exists())
        # named and pvp survive
        self.assertTrue(ObjectDB.objects.filter(pk=named_od_pk).exists())
        self.assertTrue(ObjectDB.objects.filter(pk=pvp_od_pk).exists())

        # CombatOpponent rows preserved (historical record); SET_NULL on FK.
        # Use values() to bypass the SharedMemoryModel identity-map cache and
        # read directly from the DB.
        from world.combat.models import CombatOpponent

        mook_od_id = (
            CombatOpponent.objects.filter(pk=mook.pk).values_list("objectdb_id", flat=True).first()
        )
        named_od_id = (
            CombatOpponent.objects.filter(pk=named.pk).values_list("objectdb_id", flat=True).first()
        )
        pvp_od_id = (
            CombatOpponent.objects.filter(pk=pvp.pk).values_list("objectdb_id", flat=True).first()
        )
        self.assertIsNone(mook_od_id)  # SET_NULL after ephemeral ObjectDB deleted
        self.assertIsNotNone(named_od_id)
        self.assertIsNotNone(pvp_od_id)

    def test_cleanup_nulls_the_cached_objectdb_reference_for_a_defeated_mob(self):
        """#4091 fix round 2: delete_ephemeral_npc (shared by this generic sweep
        and world.combat.won_over.delete_won_over_npc) must null the cached
        CombatOpponent's objectdb FK, not only the database row -- Evennia's
        ObjectDB.delete() nulls SET_NULL referrers via a bulk UPDATE outside
        core.deletion.IdentityMapCollector, so a held, process-cached instance
        would otherwise keep reporting the deleted body forever (mirrors
        release_companion's identical fix, world/companions/services.py).

        Uses a DEFEATED mob -- not a won-over one -- to prove the fix on the
        generic ephemeral-delete loop itself, not the won-over-specific path
        fix round 1 already covered.
        """
        from evennia.objects.models import ObjectDB

        from world.combat.constants import OpponentStatus
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent, cleanup_completed_encounter

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        mook = add_opponent(
            encounter, name="Defeated Mook", tier="mook", max_health=10, threat_pool=pool
        )
        mook.status = OpponentStatus.DEFEATED
        mook.save(update_fields=["status"])
        objectdb_pk = mook.objectdb_id

        cleanup_completed_encounter(encounter)

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        # The SAME held, process-cached instance from before cleanup ran --
        # proves the identity map is correct, not only the database row.
        self.assertIsNone(mook.objectdb_id)
        # Reading .objectdb must not raise and must not resurrect the deleted
        # body: nothing reads the deleted body through this cached reference.
        self.assertIsNone(mook.objectdb)

    def test_cleanup_does_not_evict_other_encounters_cached_opponents(self):
        """#4091 fix round 3: delete_ephemeral_npc must NOT call
        CombatOpponent.flush_instance_cache() with no arguments -- that rebuilds
        the WHOLE class cache, evicting every cached CombatOpponent in every
        live encounter (once per mob deleted in the cleanup loop). Setting
        objectdb=None and saving on the held instance is enough; no flush is
        needed at all.

        Holds a cached opponent from a DIFFERENT, still-active encounter, runs
        cleanup on the first encounter, then asserts a fresh
        ``CombatOpponent.objects.get(pk=...)`` returns the SAME object (``is``)
        -- proving the identity map for the untouched encounter was never
        evicted.
        """
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.models import CombatOpponent
        from world.combat.services import add_opponent, cleanup_completed_encounter

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        add_opponent(encounter, name="Mook", tier="mook", max_health=10, threat_pool=pool)

        other_encounter = CombatEncounterFactory()
        other_pool = ThreatPoolFactory()
        other_opponent = add_opponent(
            other_encounter, name="Other Mob", tier="mook", max_health=10, threat_pool=other_pool
        )

        cleanup_completed_encounter(encounter)

        self.assertIs(CombatOpponent.objects.get(pk=other_opponent.pk), other_opponent)

    def test_cleanup_expires_until_end_of_combat_conditions(self):
        """Generic gap (#763): a non-rite UNTIL_END_OF_COMBAT condition on an
        encounter participant is expired when the encounter completes, while a
        ROUNDS-duration condition on the same participant survives."""
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.combat.services import cleanup_completed_encounter
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
        from world.conditions.models import ConditionInstance

        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        target = participant.character_sheet.character

        end_combat_tmpl = ConditionTemplateFactory(
            name="Battle Fury", default_duration_type=DurationType.UNTIL_END_OF_COMBAT
        )
        rounds_tmpl = ConditionTemplateFactory(
            name="Bleeding", default_duration_type=DurationType.ROUNDS
        )
        end_combat_inst = ConditionInstanceFactory(
            target=target, condition=end_combat_tmpl, rounds_remaining=None
        )
        rounds_inst = ConditionInstanceFactory(
            target=target, condition=rounds_tmpl, rounds_remaining=3
        )

        cleanup_completed_encounter(encounter)

        self.assertFalse(ConditionInstance.objects.filter(pk=end_combat_inst.pk).exists())
        self.assertTrue(ConditionInstance.objects.filter(pk=rounds_inst.pk).exists())

    def test_cleanup_expires_until_end_of_combat_on_persistent_opponent(self):
        """Generic gap (#763): a persistent (non-ephemeral) NPC opponent that
        survives cleanup still has its UNTIL_END_OF_COMBAT conditions swept —
        proving the sweep, not ObjectDB deletion, clears them."""
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.services import add_opponent, cleanup_completed_encounter
        from world.conditions.constants import DurationType
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
        from world.conditions.models import ConditionInstance
        from world.scenes.factories import PersonaFactory

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        persona = PersonaFactory()  # named opponent => persistent, survives cleanup
        opp = add_opponent(
            encounter, name="Boss", tier="boss", max_health=100, threat_pool=pool, persona=persona
        )
        tmpl = ConditionTemplateFactory(
            name="Marked for Death", default_duration_type=DurationType.UNTIL_END_OF_COMBAT
        )
        inst = ConditionInstanceFactory(target=opp.objectdb, condition=tmpl, rounds_remaining=None)

        cleanup_completed_encounter(encounter)

        from evennia.objects.models import ObjectDB

        self.assertTrue(ObjectDB.objects.filter(pk=opp.objectdb_id).exists())  # opponent survived
        self.assertFalse(ConditionInstance.objects.filter(pk=inst.pk).exists())  # condition swept

    def test_cleanup_recheck_refuses_persistent_references(self):
        """Layer 5 guard: even if a corrupt row escaped Layers 1-4 and was flagged
        ephemeral despite having persistent identity references, cleanup re-checks
        and refuses to delete."""
        from evennia.objects.models import ObjectDB

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
        from world.combat.models import CombatOpponent
        from world.combat.services import cleanup_completed_encounter

        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        sheet = CharacterSheetFactory()  # has persistent FK to its ObjectDB
        # bypass clean() / DB constraint: persona is null so the DB constraint
        # doesn't trip, and we save() directly without full_clean()
        opp = CombatOpponent(
            encounter=encounter,
            name="Forged",
            tier="mook",
            max_health=20,
            health=20,
            threat_pool=pool,
            objectdb=sheet.character,
            objectdb_is_ephemeral=True,
        )
        opp.save()  # bypasses clean(); DB constraint won't trip (no persona)

        sheet_od_pk = sheet.character.pk
        cleanup_completed_encounter(encounter)

        # Layer 5 guard saved the persistent ObjectDB
        self.assertTrue(ObjectDB.objects.filter(pk=sheet_od_pk).exists())


class CleanupCompletedEncounterSustainedActionTests(TestCase):
    """Fix 3 (#2705 adversarial review): an encounter that completes early
    (kill the last enemy, GM abandons it, everyone flees) must break any
    still-pending PC ``SustainedAction`` instead of orphaning it forever —
    it would otherwise never mature, never narrate, and (RITUAL kind) its
    already-consumed components would have bought nothing."""

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_cleanup_breaks_live_sustained_ritual(self, mock_broadcast) -> None:
        from world.combat.constants import SustainedKind
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
            SustainedActionFactory,
        )
        from world.combat.models import SustainedAction
        from world.combat.services import cleanup_completed_encounter
        from world.magic.factories import RitualFactory

        encounter = CombatEncounterFactory(round_number=3)
        participant = CombatParticipantFactory(encounter=encounter)
        ritual = RitualFactory()
        sustained = SustainedActionFactory(
            encounter=encounter,
            participant=participant,
            sustained_kind=SustainedKind.RITUAL,
            technique=None,
            ritual=ritual,
            declared_action=None,
            declared_round=3,
            resolves_round=5,
            absorption_budget=3,
        )

        cleanup_completed_encounter(encounter)

        self.assertEqual(SustainedAction.objects.count(), 0)
        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_cleanup_breaks_live_sustained_technique(self, mock_broadcast) -> None:
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
            SustainedActionFactory,
        )
        from world.combat.models import SustainedAction
        from world.combat.services import cleanup_completed_encounter

        encounter = CombatEncounterFactory(round_number=3)
        participant = CombatParticipantFactory(encounter=encounter)
        sustained = SustainedActionFactory(
            encounter=encounter,
            participant=participant,
            declared_round=3,
            resolves_round=5,
            absorption_budget=3,
        )

        cleanup_completed_encounter(encounter)

        self.assertEqual(SustainedAction.objects.count(), 0)
        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertTrue(mock_broadcast.called)
