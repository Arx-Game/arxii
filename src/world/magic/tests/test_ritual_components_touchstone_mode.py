"""Tests for resolve_and_consume_ritual_components's touchstone-mode resolution (#707)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.exceptions import RitualComponentError
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
)
from world.magic.services.ritual_components import resolve_and_consume_ritual_components


class ResolveAndConsumeRitualComponentsTouchstoneModeTests(TestCase):
    def setUp(self) -> None:
        self.performer = CharacterSheetFactory()
        self.praedari = ResonanceFactory(name="Praedari")
        self.copperi = ResonanceFactory(name="Copperi")
        self.tier1 = ResonanceTierFactory(name="Faint", tier_level=1)
        self.tier2 = ResonanceTierFactory(name="Resonant", tier_level=2)
        self.ritual = RitualFactory()

    def _touchstone_instance(self, *, resonance, tier, attuned_to=None):
        template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier)
        return ItemInstanceFactory(template=template, attuned_to_character_sheet=attuned_to)

    def test_matching_attuned_touchstone_satisfies_requirement(self) -> None:
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier1, attuned_to=self.performer
        )
        resolve_and_consume_ritual_components(
            ritual=self.ritual, components=[instance], performer_sheet=self.performer
        )
        assert not ItemInstance.objects.filter(pk=instance.pk).exists()

    def test_higher_tier_satisfies_lower_requirement(self) -> None:
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier2, attuned_to=self.performer
        )
        resolve_and_consume_ritual_components(
            ritual=self.ritual, components=[instance], performer_sheet=self.performer
        )
        assert not ItemInstance.objects.filter(pk=instance.pk).exists()

    def test_unattuned_instance_does_not_satisfy(self) -> None:
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier1, attuned_to=None
        )
        with self.assertRaises(RitualComponentError) as ctx:
            resolve_and_consume_ritual_components(
                ritual=self.ritual, components=[instance], performer_sheet=self.performer
            )
        assert "attuned touchstone" in ctx.exception.user_message.lower()
        assert self.ritual.name in ctx.exception.user_message
        assert ItemInstance.objects.filter(pk=instance.pk).exists()

    def test_wrong_resonance_does_not_satisfy_without_context(self) -> None:
        """No CharacterResonance for copperi -> the copperi touchstone can't match."""
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        instance = self._touchstone_instance(
            resonance=self.copperi, tier=self.tier1, attuned_to=self.performer
        )
        with self.assertRaises(RitualComponentError):
            resolve_and_consume_ritual_components(
                ritual=self.ritual, components=[instance], performer_sheet=self.performer
            )

    def test_resonance_context_pins_the_match(self) -> None:
        """With an explicit resonance_context, only a touchstone tagged to THAT
        resonance satisfies the requirement, even if the performer holds others."""
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.copperi)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        wrong_context_instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier1, attuned_to=self.performer
        )
        with self.assertRaises(RitualComponentError):
            resolve_and_consume_ritual_components(
                ritual=self.ritual,
                components=[wrong_context_instance],
                performer_sheet=self.performer,
                resonance_context=self.copperi,
            )

    def test_template_and_touchstone_rows_both_consumed_atomically(self) -> None:
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        reagent_template = ItemTemplateFactory()
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=reagent_template, min_touchstone_tier=None
        )
        touchstone_instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier1, attuned_to=self.performer
        )
        reagent_instance = ItemInstanceFactory(template=reagent_template)
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[touchstone_instance, reagent_instance],
            performer_sheet=self.performer,
        )
        assert not ItemInstance.objects.filter(
            pk__in=[touchstone_instance.pk, reagent_instance.pk]
        ).exists()

    def test_shortfall_on_one_requirement_consumes_nothing(self) -> None:
        """Insufficient reagents must not leave the touchstone consumed."""
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.praedari)
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier1
        )
        reagent_template = ItemTemplateFactory()
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=reagent_template, min_touchstone_tier=None, quantity=2
        )
        touchstone_instance = self._touchstone_instance(
            resonance=self.praedari, tier=self.tier1, attuned_to=self.performer
        )
        reagent_instance = ItemInstanceFactory(template=reagent_template, quantity=1)
        with self.assertRaises(RitualComponentError) as ctx:
            resolve_and_consume_ritual_components(
                ritual=self.ritual,
                components=[touchstone_instance, reagent_instance],
                performer_sheet=self.performer,
            )
        assert "requires 2x" in ctx.exception.user_message
        assert "only 1 provided" in ctx.exception.user_message
        assert ItemInstance.objects.filter(pk=touchstone_instance.pk).exists()
        assert ItemInstance.objects.filter(pk=reagent_instance.pk).exists()
