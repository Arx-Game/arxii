"""Owner build-HUD + comfort fixtures (#1514 remaining scope).

The per-axis pressure/mitigation/net breakdown, the fixture place/remove
actions (first production callers of place_decoration), and the owner-gated
room-comfort endpoint. Fixtures in setUp (never setUpTestData — Evennia
objects can't survive Django's per-test deepcopy).
"""

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from actions.registry import get_action
from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import RoomDecoration
from world.buildings.seeds import ensure_decoration_kinds
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, KeyType, LocationParentType, StatKey
from world.locations.models import LocationOwnership, LocationValueModifier
from world.locations.services import room_exposure_breakdown
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)

HEARTH = "Great Hearth"


def _room_in(area, *, name="A Room", enclosure=RoomEnclosure.WALLED):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room, defaults={"area": area, "enclosure": enclosure}
    )
    return room


@tag("postgres")  # ownership cascade walks the areas_areaclosure materialized view
class ComfortHudBase(APITestCase):
    def setUp(self) -> None:
        ensure_decoration_kinds()
        self.account = AccountFactory()
        self.sheet = CharacterSheetFactory()
        self.actor = self.sheet.character
        entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=self.account))
        self.persona = self.sheet.primary_persona

        area = AreaFactory(level=AreaLevel.BUILDING)
        self.building = BuildingFactory(area=area, space_budget=100)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=self.persona,
        )
        self.room = _room_in(area, name="Hall")
        self.building.entry_room = self.room.room_profile
        self.building.save(update_fields=["entry_room"])
        self.actor.db_location = self.room
        self.actor.save(update_fields=["db_location"])

    def _chill(self, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building.area,
            key_type=KeyType.STAT,
            stat_key=StatKey.COLD,
            value=value,
        )


class BreakdownServiceTests(ComfortHudBase):
    def test_pressure_and_mitigation_decompose(self) -> None:
        self._chill(6)
        get_action("place_room_fixture").run(actor=self.actor, kind=HEARTH)

        rows = {row.stat_key: row for row in room_exposure_breakdown(self.room)}
        cold = rows[StatKey.COLD]
        self.assertEqual(cold.pressure, 6)
        self.assertEqual(cold.mitigation, 4)  # hearth PLACEHOLDER -4
        self.assertEqual(cold.net, 2)

    def test_zero_floor_never_goes_negative(self) -> None:
        self._chill(2)
        get_action("place_room_fixture").run(actor=self.actor, kind=HEARTH)
        rows = {row.stat_key: row for row in room_exposure_breakdown(self.room)}
        self.assertEqual(rows[StatKey.COLD].net, 0)
        self.assertEqual(rows[StatKey.HEAT].net, 0)  # hearth never heats the HEAT axis

    def test_sheltered_weather_axis_reports_zero_net(self) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.building.area,
            key_type=KeyType.STAT,
            stat_key=StatKey.WET,
            value=5,
        )
        rows = {row.stat_key: row for row in room_exposure_breakdown(self.room)}
        wet = rows[StatKey.WET]
        self.assertTrue(wet.sheltered)  # WALLED shelters WET
        self.assertEqual(wet.net, 0)
        self.assertEqual(wet.pressure, 5)  # HUD still shows what the roof is blocking


class FixtureActionTests(ComfortHudBase):
    def test_place_and_remove_fixture(self) -> None:
        result = get_action("place_room_fixture").run(actor=self.actor, kind=HEARTH)
        self.assertTrue(result.success, result.message)
        self.assertEqual(
            RoomDecoration.objects.filter(room_profile=self.room.room_profile).count(), 1
        )
        self.assertTrue(
            LocationValueModifier.objects.filter(
                room_profile=self.room.room_profile, stat_key=StatKey.COLD
            ).exists()
        )

        result = get_action("remove_room_fixture").run(actor=self.actor, kind=HEARTH)
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            RoomDecoration.objects.filter(room_profile=self.room.room_profile).exists()
        )
        self.assertFalse(
            LocationValueModifier.objects.filter(
                room_profile=self.room.room_profile, stat_key=StatKey.COLD
            ).exists()
        )

    def test_unknown_kind_lists_options(self) -> None:
        result = get_action("place_room_fixture").run(actor=self.actor, kind="Nonsense")
        self.assertFalse(result.success)
        self.assertIn(HEARTH, result.message)

    def test_non_owner_cannot_place(self) -> None:
        stranger = CharacterFactory()
        CharacterSheetFactory(character=stranger)
        stranger.db_location = self.room
        stranger.save(update_fields=["db_location"])
        result = get_action("place_room_fixture").run(actor=stranger, kind=HEARTH)
        self.assertFalse(result.success)


class RoomComfortEndpointTests(ComfortHudBase):
    def _url(self) -> str:
        return f"/api/buildings/manager/room/{self.room.pk}/comfort/"

    def test_owner_reads_the_hud(self) -> None:
        self._chill(6)
        get_action("place_room_fixture").run(actor=self.actor, kind=HEARTH)
        self.client.force_authenticate(user=self.account)
        response = self.client.get(self._url(), {"character_id": self.sheet.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["enclosure"], RoomEnclosure.WALLED)
        axes = {row["key"]: row for row in data["axes"]}
        self.assertEqual(axes[StatKey.COLD]["pressure"], 6)
        self.assertEqual(axes[StatKey.COLD]["mitigation"], 4)
        self.assertEqual(axes[StatKey.COLD]["net"], 2)
        self.assertEqual(len(data["fixtures"]), 1)
        self.assertGreaterEqual(len(data["fixture_kinds"]), 3)

    def test_non_owner_403(self) -> None:
        other_account = AccountFactory()
        other_sheet = CharacterSheetFactory()
        entry = RosterEntryFactory(character_sheet=other_sheet)
        RosterTenureFactory(
            roster_entry=entry, player_data=PlayerDataFactory(account=other_account)
        )
        self.client.force_authenticate(user=other_account)
        response = self.client.get(self._url(), {"character_id": other_sheet.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
