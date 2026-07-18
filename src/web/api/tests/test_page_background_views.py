"""Tests for the public page-backgrounds endpoint (#2408)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import MediaFactory, PageBackgroundFactory
from evennia_extensions.models import PageBackgroundSlot


class PageBackgroundListAPIViewTest(APITestCase):
    def test_returns_all_slots_public(self):
        media = MediaFactory(player_data=None, slug="homepage-hero")
        PageBackgroundFactory(slot=PageBackgroundSlot.HOMEPAGE, art=media)
        PageBackgroundFactory(slot=PageBackgroundSlot.ROSTER, art=None)

        response = self.client.get(reverse("api-backgrounds"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_slot = {row["slot"]: row["art_url"] for row in response.data}
        self.assertEqual(by_slot["homepage"], media.cloudinary_url)
        self.assertIsNone(by_slot["roster"])

    def test_missing_slot_omitted_not_500(self):
        response = self.client.get(reverse("api-backgrounds"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
