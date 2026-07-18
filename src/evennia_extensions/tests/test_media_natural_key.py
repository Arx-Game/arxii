"""Tests for Media's natural-key addressing (#2408)."""

from django.test import TestCase

from evennia_extensions.factories import MediaFactory
from evennia_extensions.models import Media


class MediaNaturalKeyTest(TestCase):
    def test_get_by_natural_key_resolves_slugged_row(self):
        media = MediaFactory(player_data=None, slug="homepage-hero")
        found = Media.objects.get_by_natural_key("homepage-hero")
        self.assertEqual(found.pk, media.pk)

    def test_natural_key_round_trips(self):
        media = MediaFactory(player_data=None, slug="crest-arx")
        self.assertEqual(media.natural_key(), ("crest-arx",))

    def test_player_uploaded_row_has_no_slug(self):
        media = MediaFactory()
        self.assertIsNone(media.slug)

    def test_slug_is_unique(self):
        MediaFactory(player_data=None, slug="dup-slug")
        with self.assertRaises(Exception):  # noqa: B017 - IntegrityError, driver-dependent
            MediaFactory(player_data=None, slug="dup-slug")
