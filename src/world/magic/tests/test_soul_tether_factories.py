"""Soul Tether factory wiring tests."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import wire_soul_tether_content
from world.magic.models.rituals import Ritual


class AcceptSoulTetherRitualFactoryTests(TestCase):
    """Tests for the accept_soul_tether Ritual wiring in factories."""

    def test_accept_soul_tether_ritual_has_input_schema(self) -> None:
        """The wired accept_soul_tether Ritual declares its expected kwargs."""
        wire_soul_tether_content()

        ritual = Ritual.objects.get(name="accept_soul_tether")
        self.assertIsNotNone(ritual.input_schema)
        field_names = {f["name"] for f in ritual.input_schema["fields"]}
        self.assertEqual(
            field_names,
            {"sineater_sheet_id", "scene_id", "resonance_id", "capstone_id"},
        )
