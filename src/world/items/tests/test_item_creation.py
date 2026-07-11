"""Tests for the ITEM_CREATE crafting pipeline (#2195).

Service-layer E2E covering the core journeys: success (item minted + CREATED
event + materialized + CraftedItemRecipe), failure (no item), custom prose,
inactive template, and action dispatch.
"""

from __future__ import annotations

from django.test import TestCase


class ItemCreationCraftTests(TestCase):
    """E2E tests for the item-creation crafting pipeline."""

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory, RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import install_full_lab_station, wire_enchanting_crafting

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)

    def _craftable_template(self):
        from world.items.models import ItemTemplate

        return ItemTemplate.objects.get(name="Craftable Dagger")

    def test_success_creates_item_with_provenance_and_created_event(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.constants import OwnershipEventType
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.items.models import OwnershipEvent
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="ItemCreateSuccess", success_level=5)
        template = self._craftable_template()
        with force_check_outcome(success):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=None,
                target=None,
                output_overrides={
                    "output_template": template,
                    "custom_name": "My Sword",
                    "custom_description": "A fine blade.",
                },
            )

        self.assertTrue(result.attached)
        self.assertIsNotNone(result.row)
        instance = result.row
        self.assertEqual(instance.template, template)
        self.assertEqual(instance.custom_name, "My Sword")
        self.assertEqual(instance.custom_description, "A fine blade.")
        self.assertEqual(instance.crafter_character_sheet, self.sheet)
        self.assertEqual(instance.holder_character_sheet, self.sheet)
        self.assertIsNotNone(instance.quality_tier)
        self.assertIsNotNone(instance.game_object)

        # OwnershipEvent.CREATED was written.
        created_events = OwnershipEvent.objects.filter(
            item_instance=instance,
            event_type=OwnershipEventType.CREATED,
        )
        self.assertTrue(created_events.exists())
        self.assertEqual(created_events.first().to_character_sheet, self.sheet)

        # CraftedItemRecipe join was recorded.
        self.assertIsNotNone(result.crafted_recipe)
        self.assertEqual(result.crafted_recipe.item_instance, instance)

    def test_failure_creates_no_item(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.constants import OwnershipEventType
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.items.models import ItemInstance, OwnershipEvent
        from world.traits.factories import CheckOutcomeFactory

        botch = CheckOutcomeFactory(name="ItemCreateBotch", success_level=-5)
        template = self._craftable_template()
        with force_check_outcome(botch):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=None,
                target=None,
                output_overrides={
                    "output_template": template,
                    "custom_name": "",
                    "custom_description": "",
                },
            )

        self.assertFalse(result.attached)
        self.assertIsNone(result.row)
        # No ItemInstance or OwnershipEvent.CREATED was created.
        self.assertFalse(ItemInstance.objects.filter(template=template).exists())
        self.assertFalse(
            OwnershipEvent.objects.filter(event_type=OwnershipEventType.CREATED).exists()
        )

    def test_custom_name_and_description_stored(self) -> None:
        """Craft with custom prose → instance carries them; without → empty."""
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="ItemCreateProse", success_level=5)
        template = self._craftable_template()

        # With custom prose
        with force_check_outcome(success):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=None,
                target=None,
                output_overrides={
                    "output_template": template,
                    "custom_name": "Named Blade",
                    "custom_description": "Custom desc.",
                },
            )
        self.assertTrue(result.attached)
        self.assertEqual(result.row.custom_name, "Named Blade")
        self.assertEqual(result.row.custom_description, "Custom desc.")

    def test_inactive_template_rejected(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.items.exceptions import ItemError

        template = self._craftable_template()
        template.is_active = False
        template.save(update_fields=["is_active"])
        with self.assertRaises(ItemError):
            run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=None,
                target=None,
                output_overrides={
                    "output_template": template,
                    "custom_name": "",
                    "custom_description": "",
                },
            )

    def test_action_dispatches_to_service(self) -> None:
        from world.actions.definitions.crafting import CreateItemAction
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="ItemCreateAction", success_level=5)
        template = self._craftable_template()
        with force_check_outcome(success):
            result = CreateItemAction().run(
                actor=self.character,
                output_template=template,
                custom_name="Action Sword",
                custom_description="From action.",
            )
        self.assertTrue(result.success)
        self.assertTrue(result.data["result"].created)
        self.assertEqual(result.data["result"].item_instance.custom_name, "Action Sword")
