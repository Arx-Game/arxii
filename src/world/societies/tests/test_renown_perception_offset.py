"""Tests for #738 — Society.fame_perception_offset applied in displayed tiers.

When the renown serializer is called with a ``viewer_society`` whose
``fame_perception_offset`` is non-zero, the subject's fame tier appears
shifted down by that offset (floored at NORMAL).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.constants import FAME_TIER_MULTIPLIERS, FameTier
from world.societies.factories import SocietyFactory
from world.societies.renown import set_persona_fame
from world.societies.renown_serializers import build_renown_payload


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


class PerceptionOffsetTests(TestCase):
    def test_zero_offset_shows_raw_tier(self) -> None:
        persona = _make_primary_persona()
        set_persona_fame(persona, 1_500)  # CELEBRITY (≥1000)
        society = SocietyFactory(name="Open", fame_perception_offset=0)

        payload = build_renown_payload(persona, viewer_society=society)

        self.assertEqual(payload["fame"]["tier"], FameTier.CELEBRITY.value)

    def test_negative_offset_drops_tier(self) -> None:
        persona = _make_primary_persona()
        set_persona_fame(persona, 1_500)  # CELEBRITY
        society = SocietyFactory(name="Insular", fame_perception_offset=-2)

        payload = build_renown_payload(persona, viewer_society=society)

        # CELEBRITY index 2, offset -2 → index 0 → NORMAL.
        self.assertEqual(payload["fame"]["tier"], FameTier.NORMAL.value)
        self.assertEqual(payload["fame"]["tier_multiplier"], FAME_TIER_MULTIPLIERS["normal"])

    def test_offset_floors_at_normal(self) -> None:
        persona = _make_primary_persona()
        set_persona_fame(persona, 50)  # NORMAL (already lowest)
        society = SocietyFactory(name="VeryInsular", fame_perception_offset=-4)

        payload = build_renown_payload(persona, viewer_society=society)

        self.assertEqual(payload["fame"]["tier"], FameTier.NORMAL.value)

    def test_no_viewer_society_uses_raw_tier(self) -> None:
        persona = _make_primary_persona()
        set_persona_fame(persona, 12_000)  # HOUSEHOLD_NAME

        payload = build_renown_payload(persona, viewer_society=None)

        self.assertEqual(payload["fame"]["tier"], FameTier.HOUSEHOLD_NAME.value)

    def test_offset_drops_to_intermediate_tier(self) -> None:
        persona = _make_primary_persona()
        set_persona_fame(persona, 12_000)  # HOUSEHOLD_NAME (index 3)
        society = SocietyFactory(name="MildlyInsular", fame_perception_offset=-1)

        payload = build_renown_payload(persona, viewer_society=society)

        # index 3 - 1 = 2 → CELEBRITY.
        self.assertEqual(payload["fame"]["tier"], FameTier.CELEBRITY.value)
        self.assertEqual(payload["fame"]["tier_multiplier"], FAME_TIER_MULTIPLIERS["celebrity"])
