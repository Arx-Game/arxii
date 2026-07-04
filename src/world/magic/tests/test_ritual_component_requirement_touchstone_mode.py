"""Tests for RitualComponentRequirement's touchstone-mode extension (#707)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import ItemTemplateFactory
from world.magic.factories import ResonanceTierFactory, RitualComponentRequirementFactory


class RitualComponentRequirementTouchstoneModeTests(TestCase):
    def test_template_mode_still_works(self) -> None:
        req = RitualComponentRequirementFactory()
        assert req.item_template_id is not None
        assert req.min_touchstone_tier_id is None

    def test_touchstone_mode_row(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        req = RitualComponentRequirementFactory(item_template=None, min_touchstone_tier=tier)
        assert req.item_template_id is None
        assert req.min_touchstone_tier_id == tier.pk

    def test_neither_set_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            RitualComponentRequirementFactory(item_template=None, min_touchstone_tier=None)

    def test_both_set_is_rejected(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        template = ItemTemplateFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RitualComponentRequirementFactory(item_template=template, min_touchstone_tier=tier)
