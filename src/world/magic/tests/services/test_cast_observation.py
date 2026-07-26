"""Cast observation — style concealment and per-observer detection (#2710)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import TechniqueStyleFactory


class CastConcealmentFieldTests(TestCase):
    """The content-authored dial on TechniqueStyle."""

    def test_style_defaults_to_no_concealment(self) -> None:
        """Every existing style is overt until content says otherwise."""
        style = TechniqueStyleFactory(name="Manifestation")
        self.assertEqual(style.cast_concealment, 0)

    def test_style_stores_an_authored_concealment_rating(self) -> None:
        """Concealment is a magnitude, not a flag."""
        style = TechniqueStyleFactory(name="Subtle", cast_concealment=25)
        style.refresh_from_db()
        self.assertEqual(style.cast_concealment, 25)
