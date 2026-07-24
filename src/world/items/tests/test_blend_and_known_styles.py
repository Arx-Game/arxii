"""Dye composition + exotic style knowledge (#2632)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import CharacterKnownStyle, FormValueComponent
from world.forms.services import get_presented_appearance, learn_style
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect
from world.items.services.usage import use_item


class BlendTests(TestCase):
    def setUp(self) -> None:
        self.trait = FormTraitFactory(name="hair_color", is_cosmetic=True)
        self.black = FormTraitOptionFactory(trait=self.trait, name="black", display_name="Black")
        self.green = FormTraitOptionFactory(trait=self.trait, name="green", display_name="Green")
        self.multihued = FormTraitOptionFactory(
            trait=self.trait, name="multihued", display_name="Multihued"
        )
        self.trait.composite_option = self.multihued
        self.trait.save(update_fields=["composite_option"])

        self.green_dye = ItemTemplateFactory(name="Green Dye T", is_consumable=True, max_charges=1)
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.green_dye, trait=self.trait, target_option=self.green
        )
        self.black_dye = ItemTemplateFactory(name="Black Dye T", is_consumable=True, max_charges=1)
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.black_dye, trait=self.trait, target_option=self.black
        )

        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.green)

    def _item(self, template):
        return ItemInstanceFactory(template=template, holder_character_sheet=self.sheet, charges=1)

    def test_blend_composes_components_and_normalized(self) -> None:
        """Green hair + black dye blend = Multihued with Green-Black normalized."""
        use_item(item_instance=self._item(self.black_dye), user=self.character, blend=True)

        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.multihued)
        components = list(value.components.order_by("sort_order"))
        self.assertEqual([c.option for c in components], [self.green, self.black])

        presented = {t.trait_name: t for t in get_presented_appearance(self.character)}
        self.assertEqual(presented["hair_color"].normalized, "Green-Black")

    def test_full_dye_clears_components(self) -> None:
        """A full (non-blend) dye over a blend wipes the component list."""
        use_item(item_instance=self._item(self.black_dye), user=self.character, blend=True)
        use_item(item_instance=self._item(self.green_dye), user=self.character)

        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.green)
        self.assertFalse(FormValueComponent.objects.filter(value=value).exists())

    def test_blend_unsupported_trait_refused_before_charge(self) -> None:
        from world.items.exceptions import BlendNotSupported

        style_trait = FormTraitFactory(name="hair_style", is_cosmetic=True)
        braided = FormTraitOptionFactory(trait=style_trait, name="braided")
        kit = ItemTemplateFactory(name="Kit T", is_consumable=True, max_charges=1)
        ItemTemplateAppearanceEffect.objects.create(
            item_template=kit, trait=style_trait, target_option=braided
        )
        item = self._item(kit)
        with self.assertRaises(BlendNotSupported):
            use_item(item_instance=item, user=self.character, blend=True)
        item.refresh_from_db()
        self.assertEqual(item.charges, 1)


class KnownStyleTests(TestCase):
    def setUp(self) -> None:
        self.trait = FormTraitFactory(name="hair_style", is_cosmetic=True)
        self.loose = FormTraitOptionFactory(trait=self.trait, name="loose")
        self.coils = FormTraitOptionFactory(
            trait=self.trait, name="court_coils", requires_teaching=True
        )
        self.kit = ItemTemplateFactory(name="Styling Kit T", is_consumable=False)
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.kit, trait=self.trait, target_option=None
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.loose)
        self.item = ItemInstanceFactory(
            template=self.kit, holder_character_sheet=self.sheet, charges=0
        )

    def test_unknown_exotic_refused(self) -> None:
        from world.items.exceptions import StyleNotKnown

        with self.assertRaises(StyleNotKnown):
            use_item(item_instance=self.item, user=self.character, option_id=self.coils.pk)

    def test_known_exotic_applies(self) -> None:
        learn_style(self.sheet, self.coils, taught_by_label="Test")
        use_item(item_instance=self.item, user=self.character, option_id=self.coils.pk)
        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.coils)

    def test_target_learns_by_having_it_done(self) -> None:
        """A knowing PC stylist applying an exotic style teaches the client."""
        learn_style(self.sheet, self.coils, taught_by_label="Test")
        client_sheet = CharacterSheetFactory()
        client = client_sheet.character
        client_form = CharacterFormFactory(character=client)
        CharacterFormValueFactory(form=client_form, trait=self.trait, option=self.loose)

        use_item(
            item_instance=self.item,
            user=self.character,
            target=client,
            option_id=self.coils.pk,
        )
        self.assertTrue(
            CharacterKnownStyle.objects.filter(
                character_sheet=client_sheet, option=self.coils
            ).exists()
        )

    def test_ungated_option_needs_no_knowledge(self) -> None:
        use_item(item_instance=self.item, user=self.character, option_id=self.loose.pk)
        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.loose)
