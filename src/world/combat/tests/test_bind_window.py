"""Tests for the charmed-nameless-enemy bind window (#4091 Decision 19, R3).

A charmed (ALLY_OF_CASTER) nameless enemy stays alive — bindable — after
victory, for as long as its charmer is still in the room. Turned and calmed
nameless enemies are deleted at cleanup as they were before #4091 (R3). The
window closes (and the body is deleted) either via the batch sweep
(``release_closed_bind_windows``) once the charmer leaves, or at scene finish
(``release_won_over_npcs_in_room``).

Assertions read the held, process-cached ``CombatOpponent`` instance's own
``objectdb``/``objectdb_id`` attributes directly rather than re-querying the
DB — proving ``delete_won_over_npc``'s identity-map fix (fix round 1) keeps
that cache correct, not merely the database row.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object
from evennia.objects.models import ObjectDB

from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterOutcome, OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import complete_encounter
from world.combat.won_over import (
    bind_window_open,
    delete_won_over_npc,
    release_closed_bind_windows,
    release_won_over_npcs_in_room,
    won_over_rows,
)
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.factories import PersonaFactory
from world.scenes.scene_admin_services import finish_scene_full

_ROOM_TYPECLASS = "typeclasses.rooms.Room"


class BindWindowTestsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Bind window break")
        cls.charm = ConditionTemplateFactory(
            name="Bind Window Charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        cls.turned = ConditionTemplateFactory(
            name="Bind Window Turned",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.charmer_participant = CombatParticipantFactory(encounter=self.encounter)
        self.charmer = self.charmer_participant.character_sheet.character
        self.charmer.location = self.room
        self.charmer.save()

    def _nameless_opponent(self, name: str = "Mook") -> CombatOpponent:
        return CombatOpponentFactory(encounter=self.encounter, name=name)


class CharmedNamelessKeepsBodyAfterVictoryTests(BindWindowTestsBase):
    def test_charmed_nameless_keeps_objectdb_while_charmer_present(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )

        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)

        self.assertIsNotNone(opponent.objectdb_id)
        self.assertTrue(ObjectDB.objects.filter(pk=opponent.objectdb_id).exists())

    def test_turned_nameless_still_deleted_as_today(self):
        """R3: only a charm (ALLY_OF_CASTER) opens the bind window."""
        opponent = self._nameless_opponent(name="Turned Mook")
        objectdb_pk = opponent.objectdb_id
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.turned, source_character=self.charmer
        )

        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        # This path runs through cleanup_completed_encounter's generic ephemeral
        # loop, not delete_won_over_npc (the turned/calmed cleanup predates
        # #4091 and the identity-map fix in fix round 1 is scoped to the
        # won-over bind-window deletes). The held instance's own cache stays
        # stale here (even refresh_from_db() hands back the same cached idmapper
        # instance, per core/deletion.py's documented gotcha), so this one
        # assertion reads the DB directly via values_list -- the exception to
        # "read the held instance" everywhere else in this file.
        db_value = (
            CombatOpponent.objects.filter(pk=opponent.pk)
            .values_list("objectdb_id", flat=True)
            .first()
        )
        self.assertIsNone(db_value)


class ReleaseClosedBindWindowsTests(BindWindowTestsBase):
    def test_release_deletes_once_charmer_leaves_the_room(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        objectdb_pk = opponent.objectdb_id
        self.assertIsNotNone(objectdb_pk)

        other_room = create_object(_ROOM_TYPECLASS, key="Elsewhere", nohome=True)
        self.charmer.location = other_room
        self.charmer.save()

        deleted = release_closed_bind_windows()

        self.assertEqual(deleted, 1)
        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        # The SAME process-cached opponent instance: proves the fix updates the
        # cache, not only the database row (fix round 1).
        self.assertIsNone(opponent.objectdb_id)
        self.assertIsNone(opponent.objectdb)

    def test_bind_window_open_follows_charmer_presence(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        self.assertTrue(bind_window_open(opponent))

        other_room = create_object(_ROOM_TYPECLASS, key="Elsewhere Too", nohome=True)
        self.charmer.location = other_room
        self.charmer.save()

        self.assertFalse(bind_window_open(opponent))


class DeleteWonOverNpcCacheTests(BindWindowTestsBase):
    """Fix round 1: ``delete_won_over_npc`` must keep the cached
    ``CombatOpponent`` instance honest, not only the database row."""

    def test_delete_clears_the_cached_objectdb_reference(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        opponent.status = OpponentStatus.WON_OVER
        opponent.save(update_fields=["status"])
        objectdb_pk = opponent.objectdb_id

        self.assertTrue(delete_won_over_npc(opponent))

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        self.assertIsNone(opponent.objectdb_id)
        self.assertIsNone(opponent.objectdb)
        # A second re-fetch by pk returns the SAME (now-correct) idmapper
        # instance, not a separately-cached stale one.
        refetched = CombatOpponent.objects.get(pk=opponent.pk)
        self.assertIsNone(refetched.objectdb_id)

    def test_won_over_rows_omits_the_opponent_after_delete(self):
        """The deleted, now-objectdb-less opponent never reappears as a stale
        "present" ghost row — its charm cascades away with its body, and
        ``won_over_rows`` neither crashes nor misreports it (fix round 1)."""
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        opponent.status = OpponentStatus.WON_OVER
        opponent.save(update_fields=["status"])
        viewer = self.charmer_participant.character_sheet

        rows_before = {r.opponent_id: r for r in won_over_rows(self.encounter, viewer)}
        self.assertTrue(rows_before[opponent.pk].present)
        self.assertTrue(rows_before[opponent.pk].can_bind)

        self.assertTrue(delete_won_over_npc(opponent))

        rows_after = {r.opponent_id: r for r in won_over_rows(self.encounter, viewer)}
        self.assertNotIn(opponent.pk, rows_after)


class FinishSceneFullClosesBindWindowTests(BindWindowTestsBase):
    def test_finish_scene_full_deletes_a_still_open_bind_window(self):
        from unittest.mock import patch

        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        objectdb_pk = opponent.objectdb_id
        self.assertIsNotNone(objectdb_pk)

        scene = self.encounter.scene

        with (
            patch("world.scenes.scene_admin_services.on_scene_finished"),
            patch("world.scenes.scene_admin_services.process_deferred_fatigue_resets"),
            patch("world.scenes.scene_admin_services.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        self.assertIsNone(opponent.objectdb_id)


class PersonaBackedWonOverNeverDeletedTests(BindWindowTestsBase):
    def test_persona_backed_opponent_is_never_touched(self):
        persona = PersonaFactory()
        named = CombatOpponentFactory(encounter=self.encounter, name="Road Bandit", persona=persona)
        named.objectdb.location = self.room
        named.objectdb.save()
        ConditionInstanceFactory(
            target=named.objectdb, condition=self.charm, source_character=self.charmer
        )

        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)

        self.assertTrue(ObjectDB.objects.filter(pk=named.objectdb_id).exists())
        self.assertFalse(bind_window_open(named))

        # Even with the charmer gone, the named opponent is never ephemeral, so
        # neither sweep ever touches it.
        other_room = create_object(_ROOM_TYPECLASS, key="Far Away", nohome=True)
        self.charmer.location = other_room
        self.charmer.save()

        self.assertEqual(release_closed_bind_windows(), 0)
        self.assertEqual(release_won_over_npcs_in_room(self.room), 0)
        self.assertTrue(ObjectDB.objects.filter(pk=named.objectdb_id).exists())
