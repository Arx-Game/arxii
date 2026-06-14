"""Tests for the prestige_from_fashion axis on Persona (#514).

Verifies that prestige_from_fashion is included in total_prestige when the
existing total-recompute helpers run. Uses _bump_prestige_from_deeds as the
real recompute path since it also reads all four (now five) axes to sum total.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory
from world.societies.renown import _bump_prestige_from_deeds


def _make_primary_persona():
    """Build a Character + sheet + PRIMARY persona (via the sheet FK)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


class PrestigeFromFashionAxisTest(TestCase):
    """prestige_from_fashion is the 5th prestige source axis.

    Its value must be included in total_prestige whenever any recompute
    helper fires. We exercise this by pre-seeding prestige_from_fashion
    then triggering _bump_prestige_from_deeds (which rewrites total_prestige
    as the sum of all axes).
    """

    @classmethod
    def setUpTestData(cls):
        cls.persona = _make_primary_persona()

    def test_field_defaults_to_zero(self):
        """New personas start with prestige_from_fashion == 0."""
        self.assertEqual(self.persona.prestige_from_fashion, 0)

    def test_fashion_axis_included_in_total_prestige(self):
        """total_prestige includes prestige_from_fashion after a recompute."""
        # Pre-seed fashion prestige directly (future service will do this).
        self.persona.prestige_from_fashion = 500
        self.persona.save(update_fields=["prestige_from_fashion"])

        # Fire the deeds bump — this is the real recompute helper that
        # re-derives total_prestige = sum(all axes).
        _bump_prestige_from_deeds(self.persona, delta=200)

        self.persona.refresh_from_db()
        # fashion=500, deeds=200, others default to 0 → total must be 700.
        self.assertEqual(self.persona.prestige_from_fashion, 500)
        self.assertEqual(self.persona.prestige_from_deeds, 200)
        self.assertEqual(
            self.persona.total_prestige,
            500 + 200,  # fashion + deeds
            msg="total_prestige must include prestige_from_fashion",
        )

    def test_fashion_axis_signed(self):
        """prestige_from_fashion accepts negative values (scandal path)."""
        persona = PersonaFactory()
        persona.prestige_from_fashion = -300
        persona.save(update_fields=["prestige_from_fashion"])
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_fashion, -300)
