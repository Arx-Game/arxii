"""Tests for touchstone combat resonance bonus (#2023)."""

from django.test import TestCase

from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.magic.factories import (
    ResonanceFactory,
    ResonanceTierFactory,
)
from world.magic.services.touchstone import (
    get_touchstone_cast_config,
    touchstone_cast_bonus,
)


class TouchstoneCastBonusTests(TestCase):
    """touchstone_cast_bonus sums tier-scaled bonuses from matching touchstones."""

    def test_no_touchstone_equipped_returns_zero(self):
        """No attuned touchstone equipped -> 0 bonus."""
        resonance = ResonanceFactory()

        # A character with no touchstone items equipped.
        # We need a CharacterSheet with a character that has equipped_items.
        # Using a bare object that returns an empty list for equipped_items.
        class FakeChar:
            equipped_items = []

        class FakeSheet:
            character = FakeChar()

        result = touchstone_cast_bonus(FakeSheet(), resonance)
        assert result == 0

    def test_matching_resonance_returns_bonus(self):
        """Touchstone with matching resonance -> tier_level * config_scale / 10."""
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        resonance = ResonanceFactory()
        template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier)
        item = ItemInstanceFactory(template=template)

        class FakeEquipped:
            item_instance = item

        class FakeChar:
            equipped_items = [FakeEquipped()]

        class FakeSheet:
            character = FakeChar()

        config = get_touchstone_cast_config()
        expected = tier.tier_level * config.config_scale // 10
        result = touchstone_cast_bonus(FakeSheet(), resonance)
        assert result == expected
        assert result > 0

    def test_wrong_resonance_returns_zero(self):
        """Touchstone with different resonance -> 0 bonus for the queried resonance."""
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        touchstone_resonance = ResonanceFactory()
        queried_resonance = ResonanceFactory()
        template = ItemTemplateFactory(tied_resonance=touchstone_resonance, resonance_tier=tier)
        item = ItemInstanceFactory(template=template)

        class FakeEquipped:
            item_instance = item

        class FakeChar:
            equipped_items = [FakeEquipped()]

        class FakeSheet:
            character = FakeChar()

        result = touchstone_cast_bonus(FakeSheet(), queried_resonance)
        assert result == 0

    def test_no_tied_resonance_returns_zero(self):
        """Item without tied_resonance -> 0 bonus."""
        resonance = ResonanceFactory()
        template = ItemTemplateFactory(tied_resonance=None, resonance_tier=None)
        item = ItemInstanceFactory(template=template)

        class FakeEquipped:
            item_instance = item

        class FakeChar:
            equipped_items = [FakeEquipped()]

        class FakeSheet:
            character = FakeChar()

        result = touchstone_cast_bonus(FakeSheet(), resonance)
        assert result == 0


class TouchstoneCastConfigTests(TestCase):
    def test_singleton_lazy_created(self):
        """get_touchstone_cast_config creates the singleton on first call."""
        config = get_touchstone_cast_config()
        assert config.pk == 1
        assert config.config_scale == 10  # default

    def test_singleton_idempotent(self):
        """Second call returns the same row."""
        config1 = get_touchstone_cast_config()
        config2 = get_touchstone_cast_config()
        assert config1.pk == config2.pk
