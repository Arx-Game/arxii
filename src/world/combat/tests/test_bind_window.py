"""Tests for the charmed-nameless-enemy bind window (#4091 Decision 19, R3).

A charmed (ALLY_OF_CASTER) nameless enemy stays alive — bindable — after
victory, for as long as its charmer is still in the room. Turned and calmed
nameless enemies are deleted at cleanup as they were before #4091 (R3). The
window closes (and the body is deleted) either via the batch sweep
(``release_closed_bind_windows``) once the charmer leaves, or at scene finish
(``release_won_over_npcs_in_room``).
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object
from evennia.objects.models import ObjectDB

from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterOutcome
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import complete_encounter
from world.combat.won_over import (
    bind_window_open,
    release_closed_bind_windows,
    release_won_over_npcs_in_room,
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

    def _opponent_objectdb_id(self, opponent: CombatOpponent) -> int | None:
        """Read the row's current ``objectdb_id`` straight from the DB (never trust
        a possibly-stale cached instance for this assertion)."""
        return (
            CombatOpponent.objects.filter(pk=opponent.pk)
            .values_list("objectdb_id", flat=True)
            .first()
        )


class CharmedNamelessKeepsBodyAfterVictoryTests(BindWindowTestsBase):
    def test_charmed_nameless_keeps_objectdb_while_charmer_present(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )

        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)

        objectdb_id = self._opponent_objectdb_id(opponent)
        self.assertIsNotNone(objectdb_id)
        self.assertTrue(ObjectDB.objects.filter(pk=objectdb_id).exists())

    def test_turned_nameless_still_deleted_as_today(self):
        """R3: only a charm (ALLY_OF_CASTER) opens the bind window."""
        opponent = self._nameless_opponent(name="Turned Mook")
        objectdb_pk = opponent.objectdb_id
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.turned, source_character=self.charmer
        )

        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        self.assertIsNone(self._opponent_objectdb_id(opponent))


class ReleaseClosedBindWindowsTests(BindWindowTestsBase):
    def test_release_deletes_once_charmer_leaves_the_room(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        objectdb_pk = self._opponent_objectdb_id(opponent)
        self.assertIsNotNone(objectdb_pk)

        other_room = create_object(_ROOM_TYPECLASS, key="Elsewhere", nohome=True)
        self.charmer.location = other_room
        self.charmer.save()

        deleted = release_closed_bind_windows()

        self.assertEqual(deleted, 1)
        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        self.assertIsNone(self._opponent_objectdb_id(opponent))

    def test_bind_window_open_follows_charmer_presence(self):
        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        opponent.refresh_from_db()
        self.assertTrue(bind_window_open(opponent))

        other_room = create_object(_ROOM_TYPECLASS, key="Elsewhere Too", nohome=True)
        self.charmer.location = other_room
        self.charmer.save()

        self.assertFalse(bind_window_open(opponent))


class FinishSceneFullClosesBindWindowTests(BindWindowTestsBase):
    def test_finish_scene_full_deletes_a_still_open_bind_window(self):
        from unittest.mock import patch

        opponent = self._nameless_opponent()
        ConditionInstanceFactory(
            target=opponent.objectdb, condition=self.charm, source_character=self.charmer
        )
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        objectdb_pk = self._opponent_objectdb_id(opponent)
        self.assertIsNotNone(objectdb_pk)

        scene = self.encounter.scene

        with (
            patch("world.scenes.scene_admin_services.on_scene_finished"),
            patch("world.scenes.scene_admin_services.process_deferred_fatigue_resets"),
            patch("world.scenes.scene_admin_services.broadcast_scene_message"),
        ):
            finish_scene_full(scene)

        self.assertFalse(ObjectDB.objects.filter(pk=objectdb_pk).exists())
        self.assertIsNone(self._opponent_objectdb_id(opponent))


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
