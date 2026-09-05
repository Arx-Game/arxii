"""Tests for SceneDetailSerializer.art_url (#3556).

Built in setUp rather than setUpTestData: Evennia ObjectDB instances (DbHolder)
are not deepcopyable and would break setUpTestData.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from evennia_extensions.factories import MediaFactory
from evennia_extensions.models import ObjectDisplayData
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.scenes.factories import SceneFactory
from world.scenes.serializers import SceneDetailSerializer


class SceneDetailSerializerArtUrlTestCase(TestCase):
    """art_url threads the room's resolved art (#3477 cascade) onto SceneDetail."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="ArtTestRoom", nohome=True)

    def test_no_location_yields_none(self) -> None:
        scene = SceneFactory(location=None)
        data = SceneDetailSerializer(scene).data
        assert data["art_url"] is None

    def test_no_art_anywhere_yields_none(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        self.room.room_profile.area = ward
        self.room.room_profile.save()
        scene = SceneFactory(location=self.room)
        data = SceneDetailSerializer(scene).data
        assert data["art_url"] is None

    def test_falls_back_to_area_art(self) -> None:
        ward_media = MediaFactory(player_data=None, slug="scene-ward-art")
        ward = AreaFactory(level=AreaLevel.WARD, art=ward_media)
        self.room.room_profile.area = ward
        self.room.room_profile.save()
        scene = SceneFactory(location=self.room)
        data = SceneDetailSerializer(scene).data
        assert data["art_url"] == ward_media.cloudinary_url

    def test_room_thumbnail_wins_over_area_art(self) -> None:
        ward_media = MediaFactory(player_data=None, slug="scene-ward-art-2")
        room_media = MediaFactory(player_data=None, slug="scene-room-thumbnail")
        ward = AreaFactory(level=AreaLevel.WARD, art=ward_media)
        self.room.room_profile.area = ward
        self.room.room_profile.save()
        ObjectDisplayData.objects.create(object=self.room, thumbnail=room_media)
        scene = SceneFactory(location=self.room)
        data = SceneDetailSerializer(scene).data
        assert data["art_url"] == room_media.cloudinary_url
