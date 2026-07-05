"""Tests for story-critical NPC protection in combat (#1874)."""

from django.test import TestCase
from evennia import create_object

from typeclasses.rooms import Room
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import apply_damage_to_opponent
from world.stories.factories import StoryFactory, StoryParticipationFactory
from world.stories.models import StoryNPCDependency
from world.stories.types import StoryStatus


class StoryCriticalNPCCombatTests(TestCase):
    def setUp(self) -> None:
        # Not in setUpTestData — Evennia ObjectDB instances are not deepcopyable.
        self.home_room = create_object(Room, key="NPC Home")
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
            health=10,
            max_health=10,
            soak_value=0,
        )
        self.opponent.objectdb_id = self.npc_obj.pk
        self.opponent.save(update_fields=["objectdb_id"])
        self.attacker_sheet = CharacterSheetFactory()
        self.attacker_obj = self.attacker_sheet.character
        self.story = StoryFactory(status=StoryStatus.ACTIVE)

    def test_non_participant_cannot_defeat_story_critical_npc(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        result = apply_damage_to_opponent(self.opponent, 100, source_sheet=self.attacker_sheet)
        self.opponent.refresh_from_db()
        self.assertFalse(result.defeated)
        self.assertEqual(self.opponent.status, OpponentStatus.FLED)
        self.assertGreater(self.opponent.health, 0)

    def test_participant_can_defeat_story_critical_npc(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        StoryParticipationFactory(story=self.story, character=self.attacker_obj)
        result = apply_damage_to_opponent(self.opponent, 100, source_sheet=self.attacker_sheet)
        self.opponent.refresh_from_db()
        self.assertTrue(result.defeated)
        self.assertEqual(self.opponent.status, OpponentStatus.DEFEATED)

    def test_non_story_critical_npc_defeated_normally(self):
        result = apply_damage_to_opponent(self.opponent, 100, source_sheet=self.attacker_sheet)
        self.opponent.refresh_from_db()
        self.assertTrue(result.defeated)
        self.assertEqual(self.opponent.status, OpponentStatus.DEFEATED)

    def test_no_source_sheet_still_prevented(self):
        StoryNPCDependency.objects.create(story=self.story, npc_sheet=self.npc_sheet)
        result = apply_damage_to_opponent(self.opponent, 100)
        self.opponent.refresh_from_db()
        self.assertFalse(result.defeated)
        self.assertEqual(self.opponent.status, OpponentStatus.FLED)
