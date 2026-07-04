"""Tests for ItemTemplate resonance-tie fields (#707)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.items.factories import ItemTemplateFactory
from world.magic.factories import ResonanceFactory, ResonanceTierFactory


class ItemTemplateResonanceTieTests(TestCase):
    def test_plain_item_has_no_resonance_tie(self) -> None:
        template = ItemTemplateFactory()
        assert template.tied_resonance_id is None
        assert template.resonance_tier_id is None

    def test_resonance_tied_item_carries_both_fields(self) -> None:
        resonance = ResonanceFactory(name="Praedari")
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier)
        assert template.tied_resonance_id == resonance.pk
        assert template.resonance_tier_id == tier.pk

    def test_resonance_without_tier_is_rejected_by_clean(self) -> None:
        resonance = ResonanceFactory(name="Praedari")
        template = ItemTemplateFactory.build(tied_resonance=resonance, resonance_tier=None)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_tier_without_resonance_is_rejected_by_clean(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        template = ItemTemplateFactory.build(tied_resonance=None, resonance_tier=tier)
        with self.assertRaises(ValidationError):
            template.full_clean()

    def test_resonance_without_tier_is_rejected_by_db_constraint(self) -> None:
        resonance = ResonanceFactory(name="Praedari")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemTemplateFactory(tied_resonance=resonance, resonance_tier=None)
