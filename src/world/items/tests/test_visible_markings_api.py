"""API tests for ``GET /api/items/visible-markings/`` (#2985).

The sibling of the visible-worn endpoint: same character/observer parameters,
same permission contract (self-look bypass, same-room requirement,
out-of-scope returns ``[]``), payload computed by ``visible_markings_for``.
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
from world.forms.constants import MarkingKind
from world.forms.services.markings import grant_marking
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class VisibleMarkingsAPITests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="MarkingsRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.account_a = AccountFactory(username="markings_account_a")
        self.character_a = CharacterFactory(db_key="MarkedChar", location=self.room)
        self.character_a.db_account = self.account_a
        self.character_a.save()
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        entry_a = RosterEntryFactory(character_sheet=self.sheet_a)
        RosterTenureFactory(
            roster_entry=entry_a,
            player_data=PlayerDataFactory(account=self.account_a),
            end_date=None,
        )

        self.account_b = AccountFactory(username="markings_account_b")
        self.character_b = CharacterFactory(db_key="ObserverChar", location=self.room)
        self.character_b.db_account = self.account_b
        self.character_b.save()
        sheet_b = CharacterSheetFactory(character=self.character_b)
        entry_b = RosterEntryFactory(character_sheet=sheet_b)
        RosterTenureFactory(
            roster_entry=entry_b,
            player_data=PlayerDataFactory(account=self.account_b),
            end_date=None,
        )

        self.marking = grant_marking(
            self.sheet_a,
            body_region=BodyRegion.TORSO,
            kind=MarkingKind.TATTOO,
            name="a coiled serpent tattoo",
        )
        self.client = APIClient()

    def _url(self, observer_pk: int) -> str:
        return (
            f"/api/items/visible-markings/?character={self.character_a.pk}&observer={observer_pk}"
        )

    def _wear_shirt(self) -> None:
        template = ItemTemplateFactory(name="MarkingsShirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        instance = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet_a)
        EquippedItemFactory(
            character=self.sheet_a,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character_a.equipped_items.invalidate()

    def test_same_room_observer_sees_bare_marking(self):
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(self._url(self.character_b.pk))
        assert response.status_code == 200
        names = [row["name"] for row in response.json()]
        assert "a coiled serpent tattoo" in names

    def test_clothing_conceals_from_observer_but_not_self(self):
        self._wear_shirt()
        self.client.force_authenticate(user=self.account_b)
        assert self.client.get(self._url(self.character_b.pk)).json() == []
        self.client.force_authenticate(user=self.account_a)
        names = [row["name"] for row in self.client.get(self._url(self.character_a.pk)).json()]
        assert "a coiled serpent tattoo" in names

    def test_different_room_returns_empty(self):
        elsewhere = ObjectDBFactory(
            db_key="Elsewhere",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character_b.location = elsewhere
        self.client.force_authenticate(user=self.account_b)
        assert self.client.get(self._url(self.character_b.pk)).json() == []
