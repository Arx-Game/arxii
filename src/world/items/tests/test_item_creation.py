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
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        # Link account → character via roster chain so get_account_for_character works.
        roster_entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=self.account),
        )
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
        # #2243 — the crafter authored the name/description, so they're the designer too.
        self.assertEqual(instance.designer_character_sheet, self.sheet)
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

    def test_failure_still_creates_at_the_floor(self) -> None:
        """A making never fails to create (#2886, Apostate): the prose a
        player writes into an item is the one unrecoverable ingredient. A
        failed roll lands the piece at the ladder's floor tier — discard
        (recycle) and retry, or refine it up, is the player's choice."""
        from world.checks.test_helpers import force_check_outcome
        from world.items.constants import OwnershipEventType
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.items.models import ItemInstance, OwnershipEvent, QualityTier
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

        floor = QualityTier.objects.order_by("sort_order").first()
        self.assertTrue(result.attached)
        instance = ItemInstance.objects.filter(template=template).first()
        assert instance is not None
        self.assertEqual(instance.quality_tier, floor)
        self.assertTrue(
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
        from actions.definitions.crafting import CreateItemAction
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

    def test_gated_recipe_requires_learned_knowledge(self):
        # #2242 — a requires_knowledge recipe rejects a crafter who hasn't learned it.
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.knowledge import grant_recipe_knowledge
        from world.items.crafting.models import CraftingRecipe
        from world.items.crafting.services import run_crafting_recipe
        from world.items.exceptions import RecipeNotKnown
        from world.traits.factories import CheckOutcomeFactory

        template = self._craftable_template()
        recipe = CraftingRecipe.objects.get(
            kind=CraftingRecipeKind.ITEM_CREATE, output_item_template=template
        )
        recipe.requires_knowledge = True
        recipe.save(update_fields=["requires_knowledge"])

        def _craft():
            return run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=None,
                target=None,
                output_overrides={"output_template": template},
            )

        with force_check_outcome(CheckOutcomeFactory(name="GateSuccess", success_level=5)):
            with self.assertRaises(RecipeNotKnown):
                _craft()
            # Learn it, and the same craft now proceeds.
            grant_recipe_knowledge(self.sheet, recipe)
            self.assertTrue(_craft().attached)


class StylesAtCreateTests(TestCase):
    """Create-time Style picks (#2985): designed-in registers, ambition-priced.

    A dress is Lycene from the first stitch — styles are chosen at the bench
    like accents and silhouette; STYLE_ATTACH remains the restyle path.
    """

    def setUp(self) -> None:
        from evennia_extensions.factories import AccountFactory, RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import install_full_lab_station, wire_enchanting_crafting
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        roster_entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data=PlayerDataFactory(account=self.account),
        )
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)

    def _template_with_capacity(self, capacity: int):
        from world.items.models import ItemTemplate

        template = ItemTemplate.objects.get(name="Craftable Dagger")
        template.style_capacity = capacity
        template.save(update_fields=["style_capacity"])
        return template

    def _mint_piece(self, template):
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="StyleCreateSuccess", success_level=5)
        with force_check_outcome(success):
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
        assert result.attached
        return result

    def test_style_taken_at_making_attaches_at_piece_tier(self) -> None:
        # force_check_outcome is single-shot, so (like the accent tests) the
        # sub-roll resolver is exercised directly against a minted piece.
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.services import _resolve_styles_at_create
        from world.items.factories import StyleFactory
        from world.traits.factories import CheckOutcomeFactory

        template = self._template_with_capacity(2)
        piece = self._mint_piece(template)
        lycene = StyleFactory(name="Lycene")
        with force_check_outcome(CheckOutcomeFactory(name="StyleTook", success_level=5)):
            styles = _resolve_styles_at_create(
                recipe=self.recipe,
                crafter_account=self.account,
                crafter_character=self.character,
                target_item=piece.row,
                styles_requested=[lycene],
                difficulty=0,
                tier=piece.quality_tier,
                ambition_count=1,
            )
        self.assertEqual(len(styles), 1)
        item_style = styles[0]
        self.assertEqual(item_style.style, lycene)
        self.assertEqual(item_style.item_instance, piece.row)
        self.assertEqual(item_style.attachment_quality_tier, piece.quality_tier)

    def test_over_capacity_refused_before_any_roll(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.services import run_crafting_recipe
        from world.items.exceptions import StyleCapacityExceeded
        from world.items.factories import StyleFactory
        from world.items.models import ItemInstance

        template = self._template_with_capacity(1)
        styles = [StyleFactory(name="Lycene"), StyleFactory(name="Old-Regime")]
        before = ItemInstance.objects.count()
        with self.assertRaises(StyleCapacityExceeded):
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
                    "styles": styles,
                },
            )
        self.assertEqual(ItemInstance.objects.count(), before)

    def test_weak_style_roll_makes_the_piece_without_the_register(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.crafting.services import _resolve_styles_at_create
        from world.items.factories import StyleFactory
        from world.items.models import ItemStyle
        from world.traits.factories import CheckOutcomeFactory

        template = self._template_with_capacity(1)
        piece = self._mint_piece(template)
        lycene = StyleFactory(name="Lycene")
        with force_check_outcome(CheckOutcomeFactory(name="StyleBotch", success_level=0)):
            styles = _resolve_styles_at_create(
                recipe=self.recipe,
                crafter_account=self.account,
                crafter_character=self.character,
                target_item=piece.row,
                styles_requested=[lycene],
                difficulty=0,
                tier=piece.quality_tier,
                ambition_count=1,
            )
        self.assertEqual(styles, ())
        self.assertFalse(ItemStyle.objects.filter(item_instance=piece.row).exists())
