"""Query-count regression tests for the visible-worn endpoints + service.

These tests lock in the query counts for the visibility hot path. The
visibility computation reads from ``character.equipped_items`` (the cached
``CharacterEquipmentHandler``); once that handler has loaded for a given
character, subsequent calls run zero DB queries for items, slots, or facets.

If the counts here climb, the SharedMemoryModel identity-map discipline has
been broken somewhere — likely a new ``.filter()`` / ``.get()`` /
``.values()`` call that should have walked a cached relation instead. Pin
the count, document each query, and only relax it if the new query is
genuinely necessary.
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
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services.appearance import visible_worn_items_for
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class _SharedSetupMixin:
    """Common setup: account A plays char A in room A, account B plays char B in room A.

    Char A wears five items spanning two body regions and three layers, with
    one covering layer present so layer-hiding logic actually executes.
    """

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="QCTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # Account A → character A (the worn-equipment target).
        self.account_a = AccountFactory(username="qc_account_a")
        self.character_a = CharacterFactory(db_key="QCCharA", location=self.room)
        self.character_a.db_account = self.account_a
        self.character_a.save()
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        self.entry_a = RosterEntryFactory(character_sheet=self.sheet_a)
        self.player_data_a = PlayerDataFactory(account=self.account_a)
        self.tenure_a = RosterTenureFactory(
            roster_entry=self.entry_a,
            player_data=self.player_data_a,
            end_date=None,
        )

        # Account B → character B (same-room observer).
        self.account_b = AccountFactory(username="qc_account_b")
        self.character_b = CharacterFactory(db_key="QCCharB", location=self.room)
        self.character_b.db_account = self.account_b
        self.character_b.save()
        self.sheet_b = CharacterSheetFactory(character=self.character_b)
        self.entry_b = RosterEntryFactory(character_sheet=self.sheet_b)
        self.player_data_b = PlayerDataFactory(account=self.account_b)
        self.tenure_b = RosterTenureFactory(
            roster_entry=self.entry_b,
            player_data=self.player_data_b,
            end_date=None,
        )

        # Five items on character A: three TORSO layers (one covering) + two
        # other regions. Multiple items per character ensures any per-row
        # query would multiply.
        self.items: list = []
        self._equip_item("QCShirt", BodyRegion.TORSO, EquipmentLayer.BASE, covers=False)
        self._equip_item("QCCoat", BodyRegion.TORSO, EquipmentLayer.OVER, covers=True)
        self._equip_item("QCScarf", BodyRegion.TORSO, EquipmentLayer.ACCESSORY, covers=False)
        self._equip_item("QCBoots", BodyRegion.FEET, EquipmentLayer.BASE, covers=False)
        self._equip_item("QCRing", BodyRegion.LEFT_FINGER, EquipmentLayer.ACCESSORY, covers=False)

        self.client = APIClient()

    def _equip_item(
        self,
        name: str,
        region: str,
        layer: str,
        *,
        covers: bool,
    ) -> None:
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.character_a
        item_obj.save()
        instance = ItemInstanceFactory(
            template=template,
            game_object=item_obj,
            owner=self.account_a,
        )
        EquippedItem.objects.create(
            character=self.character_a,
            item_instance=instance,
            body_region=region,
            equipment_layer=layer,
        )
        self.items.append(instance)


class VisibleWornServiceQueryCountTests(_SharedSetupMixin, TestCase):
    """The service should not run any queries when the handler is warm."""

    def test_service_runs_zero_queries_when_handler_warm(self) -> None:
        """``visible_worn_items_for`` reads from the cached
        ``character.equipped_items`` handler — once that handler has loaded
        (one DB roundtrip), the service runs zero queries for items, slots,
        or facets.
        """
        # Warm the handler explicitly.
        list(self.character_a.equipped_items)

        with self.assertNumQueries(0):
            result = visible_worn_items_for(self.character_a)
        self.assertGreater(len(result), 0)

    def test_service_first_call_loads_handler_once(self) -> None:
        """Cold call: the handler does its single load, then renders.

        Counts the queries the handler runs to fetch all five equipped
        items, their templates, quality tiers, item facets, and template
        slots in one go — then the service runs zero further queries.
        """
        # Use a fresh character so the handler is cold.
        cold_character = CharacterFactory(db_key="QCColdChar", location=self.room)
        # Equip one item to give the handler something to load.
        template = ItemTemplateFactory(name="QCColdShirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
            covers_lower_layers=False,
        )
        cold_obj = ObjectDBFactory(
            db_key="QCColdShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        cold_obj.location = cold_character
        cold_obj.save()
        cold_instance = ItemInstanceFactory(template=template, game_object=cold_obj)
        EquippedItem.objects.create(
            character=cold_character,
            item_instance=cold_instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Cold load: 1 query for EquippedItem (with select_related on
        # item_instance + template + quality_tier) + 1 prefetch for facets
        # + 1 prefetch for template slots = 3.
        with self.assertNumQueries(3):
            result = visible_worn_items_for(cold_character)
        self.assertEqual(len(result), 1)


class VisibleWornListEndpointQueryCountTests(_SharedSetupMixin, TestCase):
    """Lock in the query count for ``GET /api/items/visible-worn/?character=N``."""

    def test_same_room_observer_query_count(self) -> None:
        """Same-room observer (account B looking at character A).

        After warm-up, the endpoint runs exactly one query — the DRF
        session lookup. The two ``ObjectDB.objects.get(pk=...)`` calls
        (target + observer) hit the SharedMemoryModel identity map and
        return cached instances; ``visible_worn_items_for`` reads from
        the cached equipment handler. No RosterEntry walks.

        Pinning at 1 guards against new N+1 patterns sneaking into the
        request path.
        """
        self.client.force_authenticate(user=self.account_b)
        url = (
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_b.pk}"
        )
        # Warm-up call (loads session, equipment handler, etc.).
        self.client.get(url)

        with self.assertNumQueries(1):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class VisibleItemDetailQueryCountTests(_SharedSetupMixin, TestCase):
    """Lock in the query count for ``GET /api/items/visible-item-detail/<id>/``.

    The detail ViewSet fetches the item directly with select_related, then
    runs a permission check that derives ``wearing_character`` from
    ``item.game_object.location`` (no extra query — the FK is selected) and
    walks the cached ``equipped_items`` handler to test concealment. No
    RosterEntry queries.
    """

    def test_same_room_detail_query_count(self) -> None:
        """Same-room observer fetching a visible item.

        After warm-up, the constant-cost queries are:

        1. Session lookup (DRF auth).
        2. ItemInstance fetch with select_related (template, quality_tier,
           game_object, image, template image).

        The observer ``ObjectDB.objects.get(pk=...)`` hits the
        SharedMemoryModel identity map (warmed by prior GETs) and runs no
        query. The wearing character is derived from
        ``item.game_object.db_location`` — the FK is already in
        select_related, so the FK walk is free.
        ``_is_concealed_for_observer`` walks the cached equipped_items
        handler that was warmed by the prior GET.
        """
        # Coat was equipped at TORSO/OVER with covers_lower_layers=True —
        # it's the visible item for same-room observers.
        coat = next(item for item in self.items if item.template.name == "QCCoat")

        self.client.force_authenticate(user=self.account_b)
        url = f"/api/items/visible-item-detail/{coat.pk}/?observer={self.character_b.pk}"
        # Warm-up call (loads session, equipment handlers for observable chars).
        self.client.get(url)

        with self.assertNumQueries(2):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
