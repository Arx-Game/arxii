"""API tests for crafting-quote endpoint + consumed/consequence_label in craft results (#1031).

Covers:
- GET /api/items/item-facets/quote/ — quote returns capped max_quality_tier + affordability
- GET /api/items/item-facets/quote/ — unaffordable recipe returns affordable=false
- GET /api/items/item-facets/quote/ — non-owner gets 404
- POST /api/items/item-facets/ — craft result includes consumed + consequence_label
- GET /api/items/item-styles/quote/ — style quote works symmetrically
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    wire_enchanting_crafting,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CharacterTraitValueFactory
from world.traits.models import Trait


class CraftingApiTestCase(TestCase):
    """Base test-case: wires enchanting crafting and sets up an owner + their item."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Wire both crafting recipes with skill caps + consequence pool.
        cls.facet_recipe = wire_enchanting_crafting(base_difficulty=0)
        # Fetch the style recipe for later assertions.
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe

        cls.style_recipe = CraftingRecipe.objects.get(kind=CraftingRecipeKind.STYLE_ATTACH)

        # Owner account → character → sheet, wired via an active tenure.
        cls.owner = AccountFactory(username="quote_api_owner")
        cls.owner_char = CharacterFactory(db_key="quote_api_owner_char")
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_char)
        owner_entry = RosterEntryFactory(character_sheet=cls.owner_sheet)
        RosterTenureFactory(
            roster_entry=owner_entry,
            player_data=PlayerDataFactory(account=cls.owner),
        )
        # Give the owner an Enchanting trait value in the mid-tier band (>=40, <80 → Fine cap).
        cls.enchanting_trait = Trait.objects.get(name="Enchanting")
        CharacterTraitValueFactory(
            character=cls.owner_char,
            trait=cls.enchanting_trait,
            value=50,  # band: Fine cap (min_skill=40 → Fine tier)
        )

        # Non-owner account.
        cls.non_owner = AccountFactory(username="quote_api_nonowner")
        cls.non_owner_char = CharacterFactory(db_key="quote_api_nonowner_char")
        cls.non_owner_sheet = CharacterSheetFactory(character=cls.non_owner_char)
        non_entry = RosterEntryFactory(character_sheet=cls.non_owner_sheet)
        RosterTenureFactory(
            roster_entry=non_entry,
            player_data=PlayerDataFactory(account=cls.non_owner),
        )

        # Items.
        cls.template = ItemTemplateFactory(name="QuoteApiTemplate", facet_capacity=3)
        cls.item = ItemInstanceFactory(
            template=cls.template, holder_character_sheet=cls.owner_sheet
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)


class FacetQuoteTests(CraftingApiTestCase):
    """Tests for GET /api/items/item-facets/quote/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from evennia_extensions.factories import RoomProfileFactory
        from world.items.crafting.models import LabStationDetails
        from world.magic.factories import FacetFactory
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

        cls.facet = FacetFactory(name="QuoteApiFacet")
        # facet_recipe.requires_station defaults True (#1234) — the quote endpoint
        # narrows affordable=False without an active LAB station in the room.
        room_profile = RoomProfileFactory()
        cls.owner_char.location = room_profile.objectdb
        cls.owner_char.save()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        instance = RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind, level=1)
        LabStationDetails.objects.create(
            feature_instance=instance, durability=20, max_durability=20
        )

    def test_quote_returns_capped_max_quality_tier(self) -> None:
        """Quote endpoint returns the skill-capped max_quality_tier for the owner."""
        response = self.client.get(
            "/api/items/item-facets/quote/",
            {"item_instance": self.item.pk, "facet": self.facet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Skill=50 → Fine cap (min_skill=40); max_quality_tier should be the Fine tier.
        self.assertIsNotNone(response.data["max_quality_tier"])
        self.assertEqual(response.data["max_quality_tier"]["name"], "Fine")

    def test_quote_returns_affordable_true_when_no_cost(self) -> None:
        """Quote is affordable when recipe costs are zero (default wire_enchanting_crafting)."""
        response = self.client.get(
            "/api/items/item-facets/quote/",
            {"item_instance": self.item.pk, "facet": self.facet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["affordable"])

    def test_quote_returns_affordable_false_when_ap_insufficient(self) -> None:
        """Quote affordable=false when recipe has non-zero AP cost the crafter can't meet."""
        # Temporarily raise the AP cost to an unaffordable amount.
        self.facet_recipe.action_point_cost = 9999
        self.facet_recipe.save()
        try:
            response = self.client.get(
                "/api/items/item-facets/quote/",
                {"item_instance": self.item.pk, "facet": self.facet.pk},
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertFalse(response.data["affordable"])
        finally:
            self.facet_recipe.action_point_cost = 0
            self.facet_recipe.save()

    def test_quote_rejects_non_owner_with_404(self) -> None:
        """Non-owner requesting quote for another player's item gets 404."""
        self.client.force_authenticate(user=self.non_owner)
        response = self.client.get(
            "/api/items/item-facets/quote/",
            {"item_instance": self.item.pk, "facet": self.facet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_quote_requires_item_instance_param(self) -> None:
        """Missing item_instance param returns 400."""
        from world.magic.factories import FacetFactory

        facet = FacetFactory(name="QuoteNoItemFacet")
        response = self.client.get("/api/items/item-facets/quote/", {"facet": facet.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quote_requires_facet_param(self) -> None:
        """Missing facet param returns 400."""
        response = self.client.get("/api/items/item-facets/quote/", {"item_instance": self.item.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quote_response_shape(self) -> None:
        """Quote response contains all required top-level keys."""
        response = self.client.get(
            "/api/items/item-facets/quote/",
            {"item_instance": self.item.pk, "facet": self.facet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("costs", response.data)
        self.assertIn("affordable", response.data)
        self.assertIn("max_quality_tier", response.data)
        self.assertIn("failure_risk", response.data)
        costs = response.data["costs"]
        self.assertIn("action_points", costs)
        self.assertIn("action_points_have", costs)
        self.assertIn("anima", costs)
        self.assertIn("anima_have", costs)
        self.assertIn("materials", costs)


class FacetCraftResultConsumedTests(CraftingApiTestCase):
    """Tests that craft result includes consumed + consequence_label."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.magic.factories import FacetFactory

        cls.facet = FacetFactory(name="ConsumedFacet")
        cls.item_for_craft = ItemInstanceFactory(
            template=cls.template, holder_character_sheet=cls.owner_sheet
        )

    def test_facet_craft_result_includes_consumed_and_consequence_label(self) -> None:
        """POST craft response includes consumed dict and consequence_label string."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.factories import CheckOutcomeFactory

        with force_check_outcome(CheckOutcomeFactory(name="CraftApiSuccess", success_level=2)):
            response = self.client.post(
                "/api/items/item-facets/",
                {"item_instance": self.item_for_craft.pk, "facet": self.facet.pk},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("consumed", response.data)
        self.assertIn("consequence_label", response.data)
        # consumed is a dict with the cost keys.
        self.assertIsInstance(response.data["consumed"], dict)


class StyleQuoteTests(CraftingApiTestCase):
    """Tests for GET /api/items/item-styles/quote/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        from world.items.factories import StyleFactory

        cls.style = StyleFactory(name="QuoteApiStyle")
        cls.style_item = ItemTemplateFactory(name="StyleQuoteTemplate", style_capacity=3)
        cls.style_item_instance = ItemInstanceFactory(
            template=cls.style_item, holder_character_sheet=cls.owner_sheet
        )

    def test_style_quote_returns_capped_max_quality_tier(self) -> None:
        """Style quote endpoint returns skill-capped max_quality_tier."""
        response = self.client.get(
            "/api/items/item-styles/quote/",
            {"item_instance": self.style_item_instance.pk, "style": self.style.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["max_quality_tier"])
        self.assertEqual(response.data["max_quality_tier"]["name"], "Fine")

    def test_style_quote_rejects_non_owner_with_404(self) -> None:
        """Non-owner style quote returns 404."""
        self.client.force_authenticate(user=self.non_owner)
        response = self.client.get(
            "/api/items/item-styles/quote/",
            {"item_instance": self.style_item_instance.pk, "style": self.style.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
