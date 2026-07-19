"""Tests for PageBackground (#2408)."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import MediaFactory, PageBackgroundFactory
from evennia_extensions.models import PageBackground, PageBackgroundSlot


class PageBackgroundModelTest(TestCase):
    def test_get_by_natural_key(self):
        bg = PageBackgroundFactory(slot=PageBackgroundSlot.HOMEPAGE)
        found = PageBackground.objects.get_by_natural_key("homepage")
        self.assertEqual(found.pk, bg.pk)

    def test_slot_is_unique(self):
        PageBackgroundFactory(slot=PageBackgroundSlot.ROSTER)
        with self.assertRaises(IntegrityError):
            PageBackgroundFactory(slot=PageBackgroundSlot.ROSTER)

    def test_art_is_optional(self):
        bg = PageBackgroundFactory(slot=PageBackgroundSlot.GAME_CLIENT, art=None)
        self.assertIsNone(bg.art)

    def test_art_resolves_to_media(self):
        media = MediaFactory(player_data=None, slug="hero-art")
        bg = PageBackgroundFactory(slot=PageBackgroundSlot.CG_STAGE, art=media)
        self.assertEqual(bg.art.cloudinary_url, media.cloudinary_url)
