"""Tests for the ItemInstanceViewSet read-only carried-items endpoint."""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class ItemInstanceViewSetTests(TestCase):
    """Tests for GET /api/items/inventory/."""

    def setUp(self) -> None:
        self.user = AccountFactory(username="inventory_view_user")

        self.room = ObjectDBFactory(
            db_key="InventoryViewRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        self.character_a = CharacterFactory(
            db_key="InventoryViewCharA",
            location=self.room,
        )
        self.character_b = CharacterFactory(
            db_key="InventoryViewCharB",
            location=self.room,
        )

        # Bind both characters to the request user via active tenures so
        # the queryset-scoping in ItemInstanceViewSet returns their items.
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        self.sheet_b = CharacterSheetFactory(character=self.character_b)
        self.player_data = PlayerDataFactory(account=self.user)
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet_a),
            player_data=self.player_data,
            end_date=None,
        )
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet_b),
            player_data=self.player_data,
            end_date=None,
        )

        # Quality tier and template for the response shape.
        self.quality = QualityTierFactory(
            name="InventoryViewFine",
            color_hex="#00FF00",
        )
        self.template = ItemTemplateFactory(
            name="InventoryView Tunic",
            weight=2.5,
            size=2,
            value=15,
        )

        # Two items in character A's inventory.
        self.item_a1 = self._make_item_at(
            location=self.character_a,
            db_key="InvViewItemA1",
            quality_tier=self.quality,
        )
        self.item_a2 = self._make_item_at(
            location=self.character_a,
            db_key="InvViewItemA2",
            quality_tier=self.quality,
        )

        # One item in character B's inventory.
        self.item_b1 = self._make_item_at(
            location=self.character_b,
            db_key="InvViewItemB1",
            quality_tier=self.quality,
        )

        # One item lying in the room (location is a Room, not a Character).
        self.item_in_room = self._make_item_at(
            location=self.room,
            db_key="InvViewItemRoom",
            quality_tier=self.quality,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _make_item_at(self, *, location, db_key: str, quality_tier=None):
        """Build an ObjectDB at ``location`` and bind it to a fresh ItemInstance."""
        obj = ObjectDBFactory(
            db_key=db_key,
            db_typeclass_path="typeclasses.objects.Object",
        )
        obj.location = location
        obj.save()
        return ItemInstanceFactory(
            template=self.template,
            game_object=obj,
            quality_tier=quality_tier,
        )

    # ------------------------------------------------------------------
    # Auth guard
    # ------------------------------------------------------------------

    def test_list_unauthenticated_returns_401(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/items/inventory/?character={self.character_a.pk}")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    # ------------------------------------------------------------------
    # Filtering by character
    # ------------------------------------------------------------------

    def test_list_filters_by_character(self) -> None:
        """?character=<pk> returns only items where game_object.location == that character."""
        response = self.client.get(f"/api/items/inventory/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(result_ids, {self.item_a1.pk, self.item_a2.pk})

    def test_list_excludes_other_characters_inventory(self) -> None:
        """Items on a different character are not returned."""
        response = self.client.get(f"/api/items/inventory/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(self.item_b1.pk, result_ids)

    def test_list_excludes_items_in_rooms(self) -> None:
        """Items whose location is a room are not returned for either character."""
        response_a = self.client.get(f"/api/items/inventory/?character={self.character_a.pk}")
        response_b = self.client.get(f"/api/items/inventory/?character={self.character_b.pk}")
        a_ids = {row["id"] for row in response_a.data["results"]}
        b_ids = {row["id"] for row in response_b.data["results"]}
        self.assertNotIn(self.item_in_room.pk, a_ids)
        self.assertNotIn(self.item_in_room.pk, b_ids)

    # ------------------------------------------------------------------
    # Response shape
    # ------------------------------------------------------------------

    def test_list_includes_template_and_quality_data(self) -> None:
        """Response includes nested template and quality_tier fields."""
        response = self.client.get(f"/api/items/inventory/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertGreater(len(results), 0)
        row = results[0]

        self.assertIn("template", row)
        template = row["template"]
        self.assertEqual(template["name"], self.template.name)
        # ItemTemplateListSerializer exposes weight as a Decimal-as-string;
        # compare numerically via Decimal/str round-trip.
        self.assertEqual(str(template["weight"]).rstrip("0").rstrip("."), "2.5")
        self.assertEqual(template["size"], 2)
        self.assertEqual(template["value"], 15)

        self.assertIn("quality_tier", row)
        quality = row["quality_tier"]
        self.assertEqual(quality["color_hex"], "#00FF00")

    # ------------------------------------------------------------------
    # Permission scoping
    # ------------------------------------------------------------------

    def test_list_excludes_items_on_characters_user_does_not_play(self) -> None:
        """A non-staff user cannot see items located on a character they do not play.

        Even if they pass that character's id as a filter — the queryset scope
        runs first, the filter is just a refinement.
        """
        # Build a character the request user does NOT play.
        other_character = CharacterFactory(
            db_key="InventoryViewOtherChar",
            location=self.room,
        )
        CharacterSheetFactory(character=other_character)
        # No tenure for self.user → scope excludes other_character's items.
        other_item = self._make_item_at(
            location=other_character,
            db_key="InvViewOtherItem",
            quality_tier=self.quality,
        )

        response = self.client.get(f"/api/items/inventory/?character={other_character.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertNotIn(other_item.pk, result_ids)

    def test_staff_sees_all_items(self) -> None:
        """Staff users bypass the per-account scope."""
        staff = AccountFactory(username="inventory_view_staff", is_staff=True)
        self.client.force_authenticate(user=staff)

        # Build an item on a character the staff user does NOT play.
        other_character = CharacterFactory(
            db_key="InventoryViewStaffOtherChar",
            location=self.room,
        )
        CharacterSheetFactory(character=other_character)
        other_item = self._make_item_at(
            location=other_character,
            db_key="InvViewStaffOtherItem",
            quality_tier=self.quality,
        )

        response = self.client.get(f"/api/items/inventory/?character={other_character.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(other_item.pk, result_ids)
