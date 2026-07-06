"""Tests for the flee mechanic (#1874)."""

from django.test import TestCase
from evennia import create_object

from typeclasses.rooms import Room
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.stories.factories import StoryFactory, StoryProtectedSubjectFactory
from world.stories.flee_services import flee_story_critical_npc
from world.stories.types import StoryStatus


class FleeStoryCriticalNPCTests(TestCase):
    def setUp(self) -> None:
        # Not in setUpTestData — Evennia ObjectDB instances are not deepcopyable
        # (DbHolder), which breaks Django's per-test cls attribute copy.
        self.home_room = create_object(Room, key="NPC Home Room")
        self.room = create_object(Room, key="Combat Room")
        self.npc_sheet = CharacterSheetFactory()
        self.npc_obj = self.npc_sheet.character
        self.npc_obj.location = self.room
        self.npc_obj.db_home = self.home_room
        self.npc_obj.save(update_fields=["db_location", "db_home"])
        self.encounter = CombatEncounterFactory(room=self.room)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            persona=None,
            health=0,
            max_health=50,
            soak_value=0,
        )
        # Wire the opponent's objectdb to our NPC
        self.opponent.objectdb_id = self.npc_obj.pk
        self.opponent.save(update_fields=["objectdb_id"])
        self.attacker_sheet = CharacterSheetFactory()
        self.attacker_obj = self.attacker_sheet.character
        self.story = StoryFactory(status=StoryStatus.ACTIVE)

    def test_flee_sets_fled_status(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        flee_story_critical_npc(self.opponent, self.attacker_obj)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.status, OpponentStatus.FLED)
        self.assertGreater(self.opponent.health, 0)

    def test_flee_moves_npc_out_of_room(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        flee_story_critical_npc(self.opponent, self.attacker_obj)
        self.npc_obj.refresh_from_db()
        self.assertNotEqual(self.npc_obj.db_location_id, self.room.pk)

    def test_flee_floors_health_at_one(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        self.opponent.health = -100
        self.opponent.save(update_fields=["health"])
        flee_story_critical_npc(self.opponent, self.attacker_obj)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 1)

    def test_flee_no_attacker_still_flees(self):
        StoryProtectedSubjectFactory(story=self.story, subject_sheet=self.npc_sheet)
        flee_story_critical_npc(self.opponent, None)
        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.status, OpponentStatus.FLED)
        self.assertGreater(self.opponent.health, 0)
