"""Tests for craft_attach_style service function and API endpoint (#1151)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.exceptions import StyleAlreadyAttached, StyleCapacityExceeded
from world.items.factories import (
    ItemInstanceFactory,
    ItemStyleFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    StyleFactory,
    wire_enchanting_crafting,
)
from world.traits.factories import CharacterTraitValueFactory


class CraftAttachStyleTests(TestCase):
    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.items.factories import (
            StyleFactory,
            install_full_lab_station,
            wire_enchanting_crafting,
        )
        from world.traits.models import Trait

        # wire_enchanting_crafting seeds the Common/Fine/Masterwork tier ladder.
        wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        # requires_station defaults True (#1234) — install a Lab station in the
        # crafter's room so the pre-existing pipeline tests can still craft.
        room_profile = RoomProfileFactory()
        self.sheet.character.location = room_profile.objectdb
        self.sheet.character.save()
        install_full_lab_station(room_profile)
        template = ItemTemplateFactory(style_capacity=2)
        self.item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        self.style = StyleFactory(name="TestStyle")

    def test_success_attaches_with_resolved_tier(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemStyle
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleCraftSuccess", success_level=2)):
            result = craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )
        self.assertTrue(result.attached)
        self.assertIsNotNone(result.item_style)
        self.assertIsNotNone(result.quality_tier)
        self.assertEqual(
            ItemStyle.objects.filter(item_instance=self.item, style=self.style).count(), 1
        )
        self.assertEqual(result.item_style.attachment_quality_tier, result.quality_tier)

    def test_failed_roll_attaches_nothing(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemStyle
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleCraftBotch", success_level=-1)):
            result = craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )
        self.assertFalse(result.attached)
        self.assertIsNone(result.item_style)
        self.assertIsNone(result.quality_tier)
        self.assertFalse(ItemStyle.objects.filter(item_instance=self.item).exists())

    def test_capacity_full_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        full_item = ItemInstanceFactory(template=ItemTemplateFactory(style_capacity=0))
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRollStyle", success_level=2)
        ) as capture:
            with self.assertRaises(StyleCapacityExceeded):
                craft_attach_style(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=full_item,
                    style=self.style,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached

    def test_duplicate_style_raises_before_rolling(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.items.factories import ItemStyleFactory
        from world.items.services.crafting import craft_attach_style
        from world.traits.factories import CheckOutcomeFactory

        ItemStyleFactory(item_instance=self.item, style=self.style)
        with force_check_outcome(
            CheckOutcomeFactory(name="ShouldNotRollDupStyle", success_level=2)
        ) as capture:
            with self.assertRaises(StyleAlreadyAttached):
                craft_attach_style(
                    crafter_account=self.account,
                    crafter_character=self.sheet.character,
                    item_instance=self.item,
                    style=self.style,
                )
        self.assertIsNone(capture.check_type)  # perform_check never reached

    def test_unconfigured_check_type_raises(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe
        from world.items.exceptions import CraftingNotConfigured
        from world.items.services.crafting import craft_attach_style

        style_recipe = CraftingRecipe.objects.get(kind=CraftingRecipeKind.STYLE_ATTACH)
        style_recipe.check_type = None
        style_recipe.save()
        with self.assertRaises(CraftingNotConfigured):
            craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                style=self.style,
            )


class ItemStyleCraftViewTests(TestCase):
    """Tests for POST /api/items/item-styles/ endpoint (#1151)."""

    def setUp(self) -> None:
        from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
        from world.items.factories import install_full_lab_station
        from world.items.models import ItemInstance, ItemStyle
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.traits.models import Trait

        wire_enchanting_crafting(base_difficulty=0)
        self.quality = QualityTierFactory(
            name="StyleViewCommon", numeric_min=0, numeric_max=9999, sort_order=0
        )

        self.owner = AccountFactory(username="style_view_owner")
        self.owner_char = CharacterFactory(db_key="style_view_owner_char")
        self.owner_sheet = CharacterSheetFactory(character=self.owner_char)
        owner_entry = RosterEntryFactory(character_sheet=self.owner_sheet)
        RosterTenureFactory(
            roster_entry=owner_entry,
            player_data=PlayerDataFactory(account=self.owner),
        )
        CharacterTraitValueFactory(
            character=self.owner_sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )
        # requires_station defaults True (#1234) — install a Lab station in the
        # crafter's room so the pre-existing view tests can still craft.
        room_profile = RoomProfileFactory()
        self.owner_char.location = room_profile.objectdb
        self.owner_char.save()
        install_full_lab_station(room_profile)

        self.non_owner = AccountFactory(username="style_view_nonowner")
        self.non_owner_char = CharacterFactory(db_key="style_view_nonowner_char")
        self.non_owner_sheet = CharacterSheetFactory(character=self.non_owner_char)
        non_owner_entry = RosterEntryFactory(character_sheet=self.non_owner_sheet)
        RosterTenureFactory(
            roster_entry=non_owner_entry,
            player_data=PlayerDataFactory(account=self.non_owner),
        )

        self.template_cap2 = ItemTemplateFactory(name="StyleView Cap2 Template", style_capacity=2)
        self.template_cap1 = ItemTemplateFactory(name="StyleView Cap1 Template", style_capacity=1)
        self.template_cap0 = ItemTemplateFactory(name="StyleView Cap0 Template", style_capacity=0)

        self.item_owner = ItemInstanceFactory(
            template=self.template_cap2, holder_character_sheet=self.owner_sheet
        )
        self.item_other = ItemInstanceFactory(
            template=self.template_cap2, holder_character_sheet=self.non_owner_sheet
        )
        self.item_cap1 = ItemInstanceFactory(
            template=self.template_cap1, holder_character_sheet=self.owner_sheet
        )

        self.style_a = StyleFactory(name="ViewStyleA")
        self.style_b = StyleFactory(name="ViewStyleB")

        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        ItemStyle.flush_instance_cache()
        ItemInstance.flush_instance_cache()

    def test_post_create_calls_service(self) -> None:
        """POST rolls the crafting check and (on success) attaches the style; returns 201."""
        from world.checks.test_helpers import force_check_outcome
        from world.items.models import ItemStyle
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleViewOk", success_level=2)):
            response = self.client.post(
                "/api/items/item-styles/",
                {"item_instance": self.item_owner.pk, "style": self.style_a.pk},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["attached"])
        self.assertTrue(
            ItemStyle.objects.filter(item_instance=self.item_owner, style=self.style_a).exists()
        )

    def test_post_failed_roll_returns_200_not_attached(self) -> None:
        """POST that fails the crafting check returns 200 with attached=False."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="StyleViewBotch", success_level=-1)):
            response = self.client.post(
                "/api/items/item-styles/",
                {"item_instance": self.item_owner.pk, "style": self.style_b.pk},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["attached"])

    def test_post_rejects_non_owner(self) -> None:
        """Non-owner POST to attach a style to someone else's item is rejected with 403."""
        self.client.force_authenticate(user=self.non_owner)
        response = self.client.post(
            "/api/items/item-styles/",
            {"item_instance": self.item_owner.pk, "style": self.style_a.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_style_already_attached_returns_400(self) -> None:
        """POST same style on same item a second time returns 400 with user_message."""
        ItemStyleFactory(
            item_instance=self.item_owner, style=self.style_a, attachment_quality_tier=self.quality
        )
        response = self.client.post(
            "/api/items/item-styles/",
            {"item_instance": self.item_owner.pk, "style": self.style_a.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("That style is already attached to this item.", str(response.data))

    def test_post_capacity_exceeded_returns_400(self) -> None:
        """POST a second style on a cap-1 item returns 400."""
        ItemStyleFactory(
            item_instance=self.item_cap1, style=self.style_a, attachment_quality_tier=self.quality
        )
        response = self.client.post(
            "/api/items/item-styles/",
            {"item_instance": self.item_cap1.pk, "style": self.style_b.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This item has no remaining style slots.", str(response.data))
