"""Tests for the StartingArea/Beginnings Media-FK retrofit (#2408)."""

from django.test import TestCase

from evennia_extensions.factories import MediaFactory
from world.character_creation.factories import BeginningsFactory, StartingAreaFactory
from world.character_creation.serializers import BeginningsSerializer, StartingAreaSerializer


class CGCardArtRetrofitTest(TestCase):
    def test_starting_area_crest_image_key_sourced_from_crest_art(self):
        media = MediaFactory(player_data=None, slug="crest-arx")
        area = StartingAreaFactory(crest_art=media)
        data = StartingAreaSerializer(area).data
        self.assertEqual(data["crest_image"], media.cloudinary_url)

    def test_starting_area_crest_image_null_when_unset(self):
        area = StartingAreaFactory(crest_art=None)
        data = StartingAreaSerializer(area).data
        self.assertIsNone(data["crest_image"])

    def test_beginnings_art_image_key_sourced_from_art(self):
        media = MediaFactory(player_data=None, slug="sleeper-art")
        beginnings = BeginningsFactory(art=media)
        data = BeginningsSerializer(beginnings).data
        self.assertEqual(data["art_image"], media.cloudinary_url)

    def test_beginnings_art_image_null_when_unset(self):
        beginnings = BeginningsFactory(art=None)
        data = BeginningsSerializer(beginnings).data
        self.assertIsNone(data["art_image"])
