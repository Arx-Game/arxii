"""Tests for ItemTemplateAppearanceEffect sidecar model (#1126)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect


class ItemTemplateAppearanceEffectModelTests(TestCase):
    def test_clean_rejects_option_not_belonging_to_trait(self) -> None:
        """clean() rejects a target_option that belongs to a different trait."""
        trait_a = FormTraitFactory(name="hair_color", is_cosmetic=True)
        trait_b = FormTraitFactory(name="eye_color", is_cosmetic=True)
        option_b = FormTraitOptionFactory(trait=trait_b, name="blue")
        template = ItemTemplateFactory(name="Hair Dye Blue")
        effect = ItemTemplateAppearanceEffect(
            item_template=template, trait=trait_a, target_option=option_b
        )
        with self.assertRaises(ValidationError):
            effect.clean()

    def test_clean_rejects_non_cosmetic_trait(self) -> None:
        """clean() rejects a trait that is not cosmetically editable."""
        trait = FormTraitFactory(name="height", is_cosmetic=False)
        option = FormTraitOptionFactory(trait=trait, name="tall")
        template = ItemTemplateFactory(name="Height Potion")
        effect = ItemTemplateAppearanceEffect(
            item_template=template, trait=trait, target_option=option
        )
        with self.assertRaises(ValidationError):
            effect.clean()

    def test_clean_accepts_cosmetic_trait_with_matching_option(self) -> None:
        """clean() passes for a cosmetic trait with a matching option."""
        trait = FormTraitFactory(name="hair_color_ok", is_cosmetic=True)
        option = FormTraitOptionFactory(trait=trait, name="black")
        template = ItemTemplateFactory(name="Hair Dye Black")
        effect = ItemTemplateAppearanceEffect(
            item_template=template, trait=trait, target_option=option
        )
        effect.clean()  # should not raise

    def test_unique_constraint_one_effect_per_trait_per_template(self) -> None:
        """UniqueConstraint prevents two effects for the same (template, trait)."""
        trait = FormTraitFactory(name="hair_color_dup", is_cosmetic=True)
        option = FormTraitOptionFactory(trait=trait, name="black_dup")
        template = ItemTemplateFactory(name="Hair Dye Dup")
        ItemTemplateAppearanceEffect.objects.create(
            item_template=template, trait=trait, target_option=option
        )
        with self.assertRaises(IntegrityError):
            ItemTemplateAppearanceEffect.objects.create(
                item_template=template, trait=trait, target_option=option
            )
