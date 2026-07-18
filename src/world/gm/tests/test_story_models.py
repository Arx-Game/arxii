"""StoryArea / StoryRoomGrant model tests (#2450)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.gm.constants import GMLevel
from world.gm.factories import (
    StoryAreaFactory,
    StoryRoomGrantFactory,
    seed_default_gm_level_caps,
)
from world.gm.models import GMLevelCap


class StoryAreaTests(TestCase):
    def test_str_and_ownership_walk(self) -> None:
        story = StoryAreaFactory()
        assert story.area.story_ownership == story
        assert story.gm.story_areas.first() == story


class StoryRoomGrantTests(TestCase):
    def test_unique_per_room_and_character(self) -> None:
        grant = StoryRoomGrantFactory()
        with self.assertRaises((IntegrityError, ValidationError)):
            StoryRoomGrantFactory(room=grant.room, character=grant.character)

    def test_return_location_must_be_room(self) -> None:
        grant = StoryRoomGrantFactory()
        not_a_room = ObjectDBFactory(db_key="sword", db_typeclass_path="typeclasses.objects.Object")
        grant.return_location = not_a_room
        with self.assertRaises(ValidationError):
            grant.save()


class GMLevelCapKnobTests(TestCase):
    def test_seeded_caps_scale_with_level(self) -> None:
        GMLevelCap.objects.all().delete()
        caps = seed_default_gm_level_caps()
        assert caps[GMLevel.STARTING].max_story_areas == 1
        assert caps[GMLevel.SENIOR].max_story_areas > caps[GMLevel.STARTING].max_story_areas
        assert caps[GMLevel.SENIOR].max_story_rooms_per_area == 50
