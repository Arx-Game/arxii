"""Query-count regression tests for the refactored item endpoints.

Locks in the query budgets after the item-first / cached-handler refactor.
Each test does one warm-up GET (loads session, fills the identity map,
warms the relevant cached handler) and then asserts the query count on a
second identical GET.

If these counts climb, the SharedMemoryModel identity-map discipline has
been broken somewhere — likely a new ``.filter()`` / ``.get()`` /
``.values()`` call that should have walked a cached relation instead.

See ``test_visible_worn_query_counts.py`` for the older sibling pattern.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    OutfitFactory,
    OutfitSlotFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem, ItemFacet, ItemInstance, Outfit
from world.magic.factories import FacetFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class _OwnedCharacterMixin:
    """Account A plays character A; both live in the same room.

    Use this for any endpoint test that needs an authenticated user who
    owns a character.
    """

    def setUp(self) -> None:
        # Flush identity caches so prior tests don't leak stale handler state
        # into our assertions.
        EquippedItem.flush_instance_cache()
        ItemFacet.flush_instance_cache()
        ItemInstance.flush_instance_cache()
        Outfit.flush_instance_cache()

        self.room = ObjectDBFactory(
            db_key="ItemQCRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.account = AccountFactory(username="item_qc_account")
        self.character = CharacterFactory(db_key="ItemQCChar", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)
        self.entry = RosterEntryFactory(character_sheet=self.sheet)
        self.player_data = PlayerDataFactory(account=self.account)
        self.tenure = RosterTenureFactory(
            roster_entry=self.entry,
            player_data=self.player_data,
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)


class EquippedItemListQueryCountTests(_OwnedCharacterMixin, TestCase):
    """Lock in ``GET /api/items/equipped-items/?character=N``."""

    def setUp(self) -> None:
        super().setUp()
        template = ItemTemplateFactory(name="ItemQCShirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(
            db_key="ItemQCShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.character
        item_obj.save()
        instance = ItemInstanceFactory(template=template, game_object=item_obj)
        EquippedItem.objects.create(
            character=self.character,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def test_warm_list_query_count(self) -> None:
        """After warm-up the endpoint should not re-query the equipment handler."""
        url = f"/api/items/equipped-items/?character={self.character.pk}"
        self.client.get(url)  # warm-up
        # 1 session lookup + 1 roster permission check; handler is warm,
        # ObjectDB is identity-mapped.
        with self.assertNumQueries(2):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class ItemInstanceListQueryCountTests(_OwnedCharacterMixin, TestCase):
    """Lock in ``GET /api/items/inventory/?character=N``."""

    def setUp(self) -> None:
        super().setUp()
        template = ItemTemplateFactory(name="ItemQCInvTpl")
        for i in range(3):
            obj = ObjectDBFactory(
                db_key=f"ItemQCInvObj{i}",
                db_typeclass_path="typeclasses.objects.Object",
            )
            obj.location = self.character
            obj.save()
            ItemInstanceFactory(template=template, game_object=obj)

    def test_warm_list_query_count(self) -> None:
        url = f"/api/items/inventory/?character={self.character.pk}"
        self.client.get(url)  # warm-up
        with self.assertNumQueries(2):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class ItemFacetListQueryCountTests(_OwnedCharacterMixin, TestCase):
    """Lock in ``GET /api/items/item-facets/?item_instance=N``."""

    def setUp(self) -> None:
        super().setUp()
        template = ItemTemplateFactory(name="ItemQCFacetTpl", facet_capacity=3)
        self.quality = QualityTierFactory(name="ItemQCFacetQ", color_hex="#abcdef")
        obj = ObjectDBFactory(
            db_key="ItemQCFacetObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        obj.location = self.character
        obj.save()
        self.instance = ItemInstanceFactory(
            template=template,
            game_object=obj,
            holder_character_sheet=self.sheet,
        )
        for i in range(2):
            facet = FacetFactory(name=f"ItemQCFacet{i}")
            ItemFacetFactory(
                item_instance=self.instance,
                facet=facet,
                attachment_quality_tier=self.quality,
            )

    def test_warm_list_query_count(self) -> None:
        url = f"/api/items/item-facets/?item_instance={self.instance.pk}"
        self.client.get(url)  # warm-up
        # #684: 1 session + 1 ItemInstance fetch (prefetch served from cache
        # after warm-up via the identity map) + 1 RosterEntry permission
        # check via _user_holds_item (replaces the old account-equality check).
        with self.assertNumQueries(3):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class OutfitListQueryCountTests(_OwnedCharacterMixin, TestCase):
    """Lock in ``GET /api/items/outfits/?character_sheet=N``."""

    def setUp(self) -> None:
        super().setUp()
        wardrobe_template = ItemTemplateFactory(
            name="ItemQCWardrobeTpl",
            is_wardrobe=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="ItemQCWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            game_object=wardrobe_obj,
        )
        for i in range(2):
            OutfitFactory(
                character_sheet=self.sheet,
                wardrobe=wardrobe,
                name=f"ItemQCOutfit{i}",
            )

    def test_warm_list_query_count(self) -> None:
        url = f"/api/items/outfits/?character_sheet={self.sheet.pk}"
        self.client.get(url)  # warm-up
        # 1 session + 1 roster permission check. Sheet is identity-mapped;
        # saved_outfits handler is warm.
        with self.assertNumQueries(2):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class OutfitSlotListQueryCountTests(_OwnedCharacterMixin, TestCase):
    """Lock in ``GET /api/items/outfit-slots/?outfit=N``."""

    def setUp(self) -> None:
        super().setUp()
        wardrobe_template = ItemTemplateFactory(
            name="ItemQCSlotWardrobeTpl",
            is_wardrobe=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="ItemQCSlotWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = self.room
        wardrobe_obj.save()
        wardrobe = ItemInstanceFactory(
            template=wardrobe_template,
            game_object=wardrobe_obj,
        )
        self.outfit = OutfitFactory(
            character_sheet=self.sheet,
            wardrobe=wardrobe,
            name="ItemQCSlotOutfit",
        )
        for region, layer in (
            (BodyRegion.TORSO, EquipmentLayer.BASE),
            (BodyRegion.FEET, EquipmentLayer.BASE),
        ):
            template = ItemTemplateFactory(name=f"ItemQCSlot_{region}_{layer}")
            TemplateSlotFactory(
                template=template,
                body_region=region,
                equipment_layer=layer,
            )
            obj = ObjectDBFactory(
                db_key=f"ItemQCSlot_{region}_{layer}_obj",
                db_typeclass_path="typeclasses.objects.Object",
            )
            instance = ItemInstanceFactory(template=template, game_object=obj)
            OutfitSlotFactory(
                outfit=self.outfit,
                item_instance=instance,
                body_region=region,
                equipment_layer=layer,
            )

    def test_warm_list_query_count(self) -> None:
        url = f"/api/items/outfit-slots/?outfit={self.outfit.pk}"
        self.client.get(url)  # warm-up
        # 1 session + 1 Outfit fetch + 1 roster permission check.
        # Slots prefetch served from cache after warm-up.
        with self.assertNumQueries(3):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
