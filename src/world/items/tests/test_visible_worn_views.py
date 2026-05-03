"""Tests for VisibleWornItemViewSet and VisibleItemDetailViewSet endpoints."""

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
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class _VisibleWornSetupMixin:
    """Shared setUp for the visible-worn endpoint tests.

    Builds two rooms; in room A, account A plays character A and account B
    plays character B; in room C, account C plays character C. Character A
    wears two items: a shirt at TORSO/BASE (covered) and a coat at
    TORSO/OVER (covers_lower_layers=True). The shirt is concealed to
    same-room observers; the coat is visible.
    """

    def setUp(self) -> None:
        # Two rooms.
        self.room = ObjectDBFactory(
            db_key="VWVRoomA",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.other_room = ObjectDBFactory(
            db_key="VWVRoomB",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # Account A → character A (in room A) — the "target" being looked at.
        self.account_a = AccountFactory(username="vwv_account_a")
        self.character_a = CharacterFactory(db_key="VWVCharA", location=self.room)
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        self.entry_a = RosterEntryFactory(character_sheet=self.sheet_a)
        self.player_data_a = PlayerDataFactory(account=self.account_a)
        self.tenure_a = RosterTenureFactory(
            roster_entry=self.entry_a,
            player_data=self.player_data_a,
            end_date=None,
        )

        # Account B → character B (in room A, same room as A) — the "near observer".
        self.account_b = AccountFactory(username="vwv_account_b")
        self.character_b = CharacterFactory(db_key="VWVCharB", location=self.room)
        self.sheet_b = CharacterSheetFactory(character=self.character_b)
        self.entry_b = RosterEntryFactory(character_sheet=self.sheet_b)
        self.player_data_b = PlayerDataFactory(account=self.account_b)
        self.tenure_b = RosterTenureFactory(
            roster_entry=self.entry_b,
            player_data=self.player_data_b,
            end_date=None,
        )

        # Account C → character C (in room B, different room) — the "far observer".
        self.account_c = AccountFactory(username="vwv_account_c")
        self.character_c = CharacterFactory(db_key="VWVCharC", location=self.other_room)
        self.sheet_c = CharacterSheetFactory(character=self.character_c)
        self.entry_c = RosterEntryFactory(character_sheet=self.sheet_c)
        self.player_data_c = PlayerDataFactory(account=self.account_c)
        self.tenure_c = RosterTenureFactory(
            roster_entry=self.entry_c,
            player_data=self.player_data_c,
            end_date=None,
        )

        # Two-layer outfit on character A:
        #   - shirt at TORSO/BASE  — concealed (covered by coat)
        #   - coat at TORSO/OVER   — visible, with covers_lower_layers=True
        self.shirt_template = ItemTemplateFactory(name="VWVShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
            covers_lower_layers=False,
        )
        shirt_obj = ObjectDBFactory(
            db_key="VWVShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character_a
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
            owner=self.account_a,
        )

        self.coat_template = ItemTemplateFactory(name="VWVCoat")
        TemplateSlotFactory(
            template=self.coat_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
            covers_lower_layers=True,
        )
        coat_obj = ObjectDBFactory(
            db_key="VWVCoatObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        coat_obj.location = self.character_a
        coat_obj.save()
        self.coat = ItemInstanceFactory(
            template=self.coat_template,
            game_object=coat_obj,
            owner=self.account_a,
        )

        # Equip both on character A.
        EquippedItem.objects.create(
            character=self.character_a,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItem.objects.create(
            character=self.character_a,
            item_instance=self.coat,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
        )

        self.client = APIClient()


class VisibleWornItemViewSetTests(_VisibleWornSetupMixin, TestCase):
    """Tests for ``GET /api/items/visible-worn/?character=N``."""

    def test_unauthenticated_returns_401_or_403(self) -> None:
        """Unauthenticated requests are rejected by the permission class."""
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_same_room_observer_returns_visible_items_only(self) -> None:
        """Account B (same room) sees the coat but not the concealed shirt."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.coat.pk, ids)
        self.assertNotIn(self.shirt.pk, ids)

    def test_different_room_observer_returns_empty(self) -> None:
        """Account C (different room) sees nothing — out of scope, empty list."""
        self.client.force_authenticate(user=self.account_c)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_self_look_returns_everything_including_concealed(self) -> None:
        """Account A looking at character A sees the concealed shirt."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.shirt.pk, ids)
        self.assertIn(self.coat.pk, ids)

    def test_staff_returns_everything_from_anywhere(self) -> None:
        """Staff bypass: not in the same room, still sees concealed items."""
        staff = AccountFactory(username="vwv_staff", is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.shirt.pk, ids)
        self.assertIn(self.coat.pk, ids)

    def test_missing_character_param_returns_empty(self) -> None:
        """No ``?character=`` query → empty list (not an error)."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get("/api/items/visible-worn/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_unknown_character_id_returns_empty(self) -> None:
        """An ID that doesn't exist returns an empty list, not 404."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get("/api/items/visible-worn/?character=999999999")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class VisibleItemDetailViewSetTests(_VisibleWornSetupMixin, TestCase):
    """Tests for ``GET /api/items/visible-item-detail/<id>/``."""

    def test_detail_visible_item_returns_full_data(self) -> None:
        """Account B (same room) can fetch the visible coat — full payload."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(f"/api/items/visible-item-detail/{self.coat.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.coat.pk)
        # The detail serializer mirrors ItemInstanceReadSerializer — confirm
        # the nested template payload is present (not just an id).
        self.assertEqual(response.data["template"]["name"], "VWVCoat")

    def test_detail_concealed_item_returns_404(self) -> None:
        """A concealed shirt is hidden — non-staff non-self gets 404."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(f"/api/items/visible-item-detail/{self.shirt.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_staff_can_fetch_concealed(self) -> None:
        """Staff bypass: concealed item is reachable."""
        staff = AccountFactory(username="vwv_detail_staff", is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-item-detail/{self.shirt.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.shirt.pk)

    def test_detail_item_from_another_room_returns_404(self) -> None:
        """Account C is in a different room → both items are out of scope (404)."""
        self.client.force_authenticate(user=self.account_c)
        coat_response = self.client.get(f"/api/items/visible-item-detail/{self.coat.pk}/")
        self.assertEqual(coat_response.status_code, status.HTTP_404_NOT_FOUND)
        shirt_response = self.client.get(f"/api/items/visible-item-detail/{self.shirt.pk}/")
        self.assertEqual(shirt_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_self_can_fetch_concealed(self) -> None:
        """Self-look: account A can fetch the concealed shirt on character A."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(f"/api/items/visible-item-detail/{self.shirt.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.shirt.pk)
