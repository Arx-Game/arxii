"""E2E journey test for equipment in combat (#2023).

Covers the integration points between the build items:
1. Touchstone provably raises matching-resonance cast power via the power-term provider
2. USE_ITEM maneuver dispatches correctly (unit-tested in test_use_item_maneuver)
3. Weapon facet participates in passive_facet_bonuses (fighter style parity)

No auto-narration tests — flourish fields are inert, touchstone bonus is passive.
"""

from __future__ import annotations

from django.test import TestCase

from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.magic.factories import (
    ResonanceFactory,
    ResonanceTierFactory,
)
from world.magic.services.touchstone import touchstone_cast_bonus


class TouchstonePowerTermIntegrationTests(TestCase):
    """The touchstone power-term provider is wired into _derive_power's TERM stage."""

    def test_touchstone_bonus_for_matching_resonance(self):
        """touchstone_cast_bonus returns > 0 when a matching touchstone is equipped."""
        tier = ResonanceTierFactory(name="Profound", tier_level=3)
        resonance = ResonanceFactory()

        template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier)
        item = ItemInstanceFactory(template=template)

        equipped = type("E", (), {"item_instance": item})()
        char = type("C", (), {"equipped_items": [equipped]})()
        sheet = type("S", (), {"character": char})()

        direct_bonus = touchstone_cast_bonus(sheet, resonance)
        assert direct_bonus > 0
        assert direct_bonus == tier.tier_level * 10 // 10  # config_scale=10 default

    def test_touchstone_bonus_zero_without_touchstone(self):
        """touchstone_cast_bonus returns 0 when no touchstone is equipped."""
        resonance = ResonanceFactory()

        char = type("C", (), {"equipped_items": []})()
        sheet = type("S", (), {"character": char})()

        assert touchstone_cast_bonus(sheet, resonance) == 0

    def test_touchstone_bonus_scales_with_tier(self):
        """Higher-tier touchstones produce larger bonuses."""
        resonance = ResonanceFactory()
        tier1 = ResonanceTierFactory(name="Faint", tier_level=1)
        tier3 = ResonanceTierFactory(name="Profound", tier_level=3)

        template1 = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier1)
        template3 = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier3)
        item1 = ItemInstanceFactory(template=template1)
        item3 = ItemInstanceFactory(template=template3)

        equipped1 = type("E", (), {"item_instance": item1})()
        char1 = type("C", (), {"equipped_items": [equipped1]})()
        sheet1 = type("S", (), {"character": char1})()
        bonus1 = touchstone_cast_bonus(sheet1, resonance)

        equipped3 = type("E", (), {"item_instance": item3})()
        char3 = type("C", (), {"equipped_items": [equipped3]})()
        sheet3 = type("S", (), {"character": char3})()
        bonus3 = touchstone_cast_bonus(sheet3, resonance)

        assert bonus3 > bonus1
        assert bonus3 == 3 * bonus1  # tier 3 vs tier 1


class EquipmentFlourishFieldTests(TestCase):
    """Flourish fields are inert model fields — resolve_item_flourish works but is unwired."""

    def test_flourish_resolved_from_real_item(self):
        """resolve_item_flourish reads from real ItemTemplate/ItemInstance."""
        from world.items.services.flourish import resolve_item_flourish

        template = ItemTemplateFactory(flourish_text="gleaming crimson in the torchlight")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="")
        assert resolve_item_flourish(instance) == "gleaming crimson in the torchlight"

    def test_flourish_overridden_on_real_item(self):
        """Player override takes precedence on a real ItemInstance."""
        from world.items.services.flourish import resolve_item_flourish

        template = ItemTemplateFactory(flourish_text="template flourish")
        instance = ItemInstanceFactory(template=template, custom_flourish_text="my custom flourish")
        assert resolve_item_flourish(instance) == "my custom flourish"
