"""Gift model tests."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import GiftFactory, TechniqueStyleFactory


class GiftStyleTests(TestCase):
    """Gift.style — the casting style a gift can impose, overriding the caster's Path (#2905)."""

    def test_style_defaults_to_none(self) -> None:
        """A gift that hasn't opted in defers to the caster's Path, as before."""
        gift = GiftFactory()
        self.assertIsNone(gift.style)

    def test_style_can_be_set_and_persists(self) -> None:
        style = TechniqueStyleFactory(cast_concealment=25)
        gift = GiftFactory(style=style)
        gift.refresh_from_db()
        self.assertEqual(gift.style, style)
