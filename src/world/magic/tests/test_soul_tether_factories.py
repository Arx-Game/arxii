"""Soul Tether factory wiring tests."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import wire_soul_tether_content
from world.magic.models.rituals import Ritual


class AcceptSoulTetherRitualFactoryTests(TestCase):
    """Tests for the accept_soul_tether Ritual wiring in factories (Slice B BILATERAL)."""

    def test_accept_soul_tether_ritual_has_input_schema(self) -> None:
        """The wired accept_soul_tether Ritual declares its BILATERAL session kwargs."""
        wire_soul_tether_content()

        ritual = Ritual.objects.get(name="accept_soul_tether")
        self.assertIsNotNone(ritual.input_schema)
        field_names = {f["name"] for f in ritual.input_schema["fields"]}
        # Slice B: session-level fields (resonance_id, writeup) — no sineater_sheet_id
        # because partner identity comes from participation, not session_kwargs.
        self.assertEqual(field_names, {"resonance_id", "writeup"})
        participant_field_names = {f["name"] for f in ritual.input_schema["participant_fields"]}
        self.assertEqual(participant_field_names, {"soul_tether_role"})
