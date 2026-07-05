"""Unit tests for the ENVIRONMENTAL_DETAIL target-search candidate helper (#882)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.missions.target_queries import environmental_detail_candidates


class EnvironmentalDetailCandidatesTests(TestCase):
    def test_excludes_character_room_exit(self) -> None:
        character = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character")
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_typeclass_path="typeclasses.exits.Exit")
        prop = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")

        candidates = environmental_detail_candidates()

        self.assertIn(prop, candidates)
        self.assertNotIn(character, candidates)
        self.assertNotIn(room, candidates)
        self.assertNotIn(exit_obj, candidates)
