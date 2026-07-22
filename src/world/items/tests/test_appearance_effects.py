"""Tests for ItemTemplateAppearanceEffect sidecar model + use_item integration (#1126)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import AppearanceChangeLog
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect
from world.items.services.usage import use_item


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


class UseItemAppearanceEffectTests(TestCase):
    """Integration tests: use_item applies cosmetic appearance effects (#1126)."""

    def setUp(self) -> None:
        self.trait = FormTraitFactory(name="hair_color_use", is_cosmetic=True)
        self.black = FormTraitOptionFactory(trait=self.trait, name="black")
        self.blonde = FormTraitOptionFactory(trait=self.trait, name="blonde")
        self.template = ItemTemplateFactory(
            name="Hair Dye Blonde",
            is_consumable=True,
            max_charges=1,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=self.trait,
            target_option=self.blonde,
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.persona = self.sheet.primary_persona
        self.form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(
            form=self.form,
            trait=self.trait,
            option=self.black,
        )
        self.item = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.sheet,
            charges=1,
        )

    def test_use_item_applies_cosmetic_change(self) -> None:
        """use_item on a cosmetic dye edits the real form's trait value."""
        result = use_item(item_instance=self.item, user=self.character)
        self.form.refresh_from_db()
        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.blonde)
        self.assertEqual(value.natural_option, self.black)
        self.assertEqual(len(result.appearance_changes), 1)
        self.assertEqual(result.charges_remaining, 0)
        self.assertTrue(result.destroyed)

    def test_use_item_writes_appearance_change_log(self) -> None:
        """use_item writes an AppearanceChangeLog row with from/to + note."""
        use_item(item_instance=self.item, user=self.character)
        log = AppearanceChangeLog.objects.get(form=self.form)
        self.assertEqual(log.from_option, self.black)
        self.assertEqual(log.to_option, self.blonde)
        self.assertEqual(log.note, "Hair Dye Blonde")

    def test_use_item_no_pool_still_applies_appearance(self) -> None:
        """A cosmetic item with no on_use_pool still applies appearance effects."""
        # Template already has no on_use_pool (factory defaults to None)
        result = use_item(item_instance=self.item, user=self.character)
        self.assertEqual(len(result.appearance_changes), 1)

    def test_use_item_no_appearance_effects_returns_empty(self) -> None:
        """A non-cosmetic usable item returns empty appearance_changes."""
        from actions.factories import ConsequencePoolFactory

        pool = ConsequencePoolFactory()
        plain_template = ItemTemplateFactory(
            name="Plain Potion",
            is_consumable=True,
            max_charges=1,
        )
        plain_template.on_use_pool = pool
        plain_template.save()
        plain_item = ItemInstanceFactory(
            template=plain_template,
            holder_character_sheet=self.sheet,
            charges=1,
        )
        result = use_item(item_instance=plain_item, user=self.character)
        self.assertEqual(result.appearance_changes, [])

    def test_use_item_reusable_not_consumed(self) -> None:
        """A reusable (non-consumable) cosmetic item applies effects without destruction."""
        reusable_template = ItemTemplateFactory(
            name="Makeup Kit",
            is_consumable=False,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=reusable_template,
            trait=self.trait,
            target_option=self.blonde,
        )
        reusable_item = ItemInstanceFactory(
            template=reusable_template,
            holder_character_sheet=self.sheet,
        )
        result = use_item(item_instance=reusable_item, user=self.character)
        self.assertEqual(len(result.appearance_changes), 1)
        self.assertFalse(result.destroyed)


class PCStylistTests(TestCase):
    """Styling another character with a cosmetic item (#2632)."""

    def setUp(self) -> None:
        self.trait = FormTraitFactory(name="hair_color_stylist", is_cosmetic=True)
        self.black = FormTraitOptionFactory(trait=self.trait, name="raven")
        self.crimson = FormTraitOptionFactory(trait=self.trait, name="crimson")
        self.template = ItemTemplateFactory(
            name="Crimson Dye",
            is_consumable=True,
            max_charges=1,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=self.trait,
            target_option=self.crimson,
        )
        self.stylist_sheet = CharacterSheetFactory()
        self.stylist = self.stylist_sheet.character
        self.client_sheet = CharacterSheetFactory()
        self.client_char = self.client_sheet.character
        self.client_form = CharacterFormFactory(character=self.client_char)
        CharacterFormValueFactory(
            form=self.client_form,
            trait=self.trait,
            option=self.black,
        )
        self.item = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.stylist_sheet,
            charges=1,
        )

    def _tenure_for(self, sheet):
        from evennia_extensions.factories import AccountFactory
        from evennia_extensions.models import PlayerData
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory(character_sheet=sheet)
        return RosterTenureFactory(player_data=player_data, roster_entry=entry)

    def test_styling_npc_target_applies_to_their_form(self) -> None:
        """No active tenure on the target -> NPC, no consent gate."""
        result = use_item(item_instance=self.item, user=self.stylist, target=self.client_char)
        value = self.client_form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.crimson)
        self.assertEqual(len(result.appearance_changes), 1)

    def test_styling_player_target_blocked_by_default(self) -> None:
        """Makeover category defaults to allowlist — strangers are refused, no charge burnt."""
        from world.items.exceptions import MakeoverNotPermitted

        self._tenure_for(self.client_sheet)
        with self.assertRaises(MakeoverNotPermitted):
            use_item(item_instance=self.item, user=self.stylist, target=self.client_char)
        self.item.refresh_from_db()
        self.assertEqual(self.item.charges, 1)
        value = self.client_form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.black)

    def test_styling_whitelisted_stylist_allowed(self) -> None:
        """A whitelisted stylist restyles the target's real form; stylist is the actor."""
        from world.consent.services import add_social_consent_whitelist, makeover_category
        from world.forms.models import AppearanceChangeLog

        owner_tenure = self._tenure_for(self.client_sheet)
        stylist_tenure = self._tenure_for(self.stylist_sheet)
        add_social_consent_whitelist(owner_tenure, stylist_tenure, makeover_category())

        use_item(item_instance=self.item, user=self.stylist, target=self.client_char)
        value = self.client_form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.crimson)
        log = AppearanceChangeLog.objects.get(form=self.client_form)
        self.assertEqual(log.note, "Crimson Dye")

    def test_styling_self_unaffected_by_gate(self) -> None:
        """Passing target=user behaves as self-makeover (no consent check)."""
        stylist_form = CharacterFormFactory(character=self.stylist)
        CharacterFormValueFactory(form=stylist_form, trait=self.trait, option=self.black)
        self._tenure_for(self.stylist_sheet)
        result = use_item(item_instance=self.item, user=self.stylist, target=self.stylist)
        self.assertEqual(len(result.appearance_changes), 1)


class DescriptorFlavorTests(TestCase):
    """Multi-color hair: free-text descriptors ride cosmetic item uses (#2632)."""

    def setUp(self) -> None:
        self.trait = FormTraitFactory(name="hair_color_flavor", is_cosmetic=True)
        self.black = FormTraitOptionFactory(trait=self.trait, name="onyx")
        self.silver = FormTraitOptionFactory(trait=self.trait, name="silver")
        self.template = ItemTemplateFactory(
            name="Silver Dye",
            is_consumable=True,
            max_charges=2,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template,
            trait=self.trait,
            target_option=self.silver,
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.persona = self.sheet.primary_persona
        self.form = CharacterFormFactory(character=self.character)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.black)
        self.item = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.sheet,
            charges=2,
        )

    def test_descriptor_sets_presentation_flavor(self) -> None:
        from world.forms.models import PersonaTraitDescriptor

        use_item(
            item_instance=self.item,
            user=self.character,
            descriptor="onyx shot through with silver streaks",
        )
        row = PersonaTraitDescriptor.objects.get(persona=self.persona, trait=self.trait)
        self.assertEqual(row.text, "onyx shot through with silver streaks")

    def test_use_without_descriptor_clears_stale_flavor(self) -> None:
        from world.forms.models import PersonaTraitDescriptor

        use_item(
            item_instance=self.item,
            user=self.character,
            descriptor="onyx shot through with silver streaks",
        )
        self.item.refresh_from_db()
        use_item(item_instance=self.item, user=self.character)
        self.assertFalse(
            PersonaTraitDescriptor.objects.filter(persona=self.persona, trait=self.trait).exists()
        )
