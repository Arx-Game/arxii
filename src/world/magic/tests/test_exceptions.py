"""Tests for magic app typed exceptions."""

from django.test import SimpleTestCase

from world.magic.exceptions import NoMatchingWornFacetItemsError


class NoMatchingWornFacetItemsErrorTests(SimpleTestCase):
    def test_user_message(self) -> None:
        exc = NoMatchingWornFacetItemsError()
        self.assertEqual(exc.user_message, "You aren't wearing anything bearing this facet.")
