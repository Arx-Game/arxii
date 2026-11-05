"""Carving the map (#4905): staff give a domain its pips through the web dispatch,
take a gesture back with the pips going to whoever held them before, and clear a
domain in one go while its children keep their ground."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.areas.tests.test_worldmap import tiny_map
from world.areas.worldmap.models import AreaFootprintPip
from world.areas.worldmap.services import (
    create_region_map,
    holder_at,
    import_region_map_file,
)
from world.character_creation.factories import RealmFactory
from world.societies.houses.almanach import plant_rung, rung_area_for_title
from world.societies.houses.constants import TitleTier


class CarvingTheMapJourney(JourneyCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=cls.region, file_name="t.map", data=tiny_map().encode())
        cls.realm = RealmFactory(name="Umbros")
        cls.kingdom = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="The Umbral Empire")
        cls.duchy = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Luxen", parent_title=cls.kingdom
        )
        cls.county = plant_rung(
            realm=cls.realm, tier=TitleTier.COUNTY, name="Salvation", parent_title=cls.duchy
        )

    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Map Room")
        self.staff = self.make_player("Apostate", room=room)
        account = self.account_of(self.staff)
        account.is_staff = True
        account.save()
        self.player = self.make_player("Hobb", room=room)

    def test_a_fill_an_undo_that_restores_prior_holders_and_a_clear(self) -> None:
        kingdom_area = rung_area_for_title(self.kingdom)
        county_area = rung_area_for_title(self.county)
        # the realm takes its island
        result = self.web(
            self.staff, "atlas_carve_footprint", title_id=self.kingdom.pk, add=[[1, 1], [2, 1]]
        )
        assert result.detail.success, result.detail.message
        assert result.detail.data["changed"] == [
            [1, 1, None, kingdom_area.pk],
            [2, 1, None, kingdom_area.pk],
        ]
        # a county carved out of the realm's land, then undone: the pip goes back to the
        # realm, not to the duchy an inverse carve would hand it to
        carved = self.web(
            self.staff, "atlas_carve_footprint", title_id=self.county.pk, add=[[1, 1], [3, 1]]
        )
        assert carved.detail.data["changed"] == [
            [1, 1, kingdom_area.pk, county_area.pk],
            [3, 1, None, county_area.pk],
        ]
        undone = self.web(
            self.staff,
            "atlas_restore_footprint",
            pips=[[x, y, before] for x, y, before, _after in carved.detail.data["changed"]],
        )
        assert undone.detail.success, undone.detail.message
        assert undone.detail.data == {"restored": 2}
        assert holder_at(1, 1) == kingdom_area
        assert holder_at(3, 1) is None
        # clear leaves the children where they stand
        self.web(self.staff, "atlas_carve_footprint", title_id=self.county.pk, add=[[2, 1]])
        cleared = self.web(self.staff, "atlas_clear_footprint", title_id=self.kingdom.pk)
        assert cleared.detail.success, cleared.detail.message
        assert cleared.detail.message == "The Umbral Empire: 1 pips cleared."
        assert holder_at(1, 1) is None
        assert holder_at(2, 1) == county_area
        # a player is refused at every one of the three seams
        for key, kwargs in (
            ("atlas_carve_footprint", {"title_id": self.kingdom.pk, "add": [[5, 5]]}),
            ("atlas_clear_footprint", {"title_id": self.county.pk}),
            ("atlas_restore_footprint", {"pips": [[1, 1, kingdom_area.pk]]}),
        ):
            refused = self.web(self.player, key, **kwargs)
            assert not refused.detail.success, key
        assert AreaFootprintPip.objects.filter(x=5, y=5).count() == 0

    def test_adjust_takes_from_the_neighbour_and_undo_gives_it_back_and_a_seat_drags(self) -> None:
        """#4988: Adjust moves a strip from one county to its sibling in one stroke, undo puts
        it back on the sibling; a seat drag moves the barony's pip and refuses a pip outside."""
        from world.areas.worldmap.services import holder_at
        from world.societies.houses.constants import TitleTier
        from world.societies.houses.models import Title

        duchy = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=self.kingdom
        )
        west = plant_rung(realm=self.realm, tier=TitleTier.COUNTY, name="West", parent_title=duchy)
        east = plant_rung(realm=self.realm, tier=TitleTier.COUNTY, name="East", parent_title=duchy)
        west_area = rung_area_for_title(west)
        east_area = rung_area_for_title(east)
        self.web(
            self.staff, "atlas_carve_footprint", title_id=east.pk, add=[[2, 1], [2, 2], [2, 3]]
        )
        plain = self.web(
            self.staff, "atlas_carve_footprint", title_id=west.pk, add=[[2, 1], [2, 2]]
        )
        assert plain.detail.data["added"] == 0
        adjusted = self.web(
            self.staff,
            "atlas_carve_footprint",
            title_id=west.pk,
            add=[[2, 1], [2, 2]],
            take_from_siblings=True,
        )
        assert adjusted.detail.success, adjusted.detail.message
        assert adjusted.detail.data["changed"] == [
            [2, 1, east_area.pk, west_area.pk],
            [2, 2, east_area.pk, west_area.pk],
        ]
        undone = self.web(
            self.staff,
            "atlas_restore_footprint",
            pips=[[x, y, before] for x, y, before, _after in adjusted.detail.data["changed"]],
        )
        assert undone.detail.success
        assert holder_at(2, 1) == east_area
        assert holder_at(2, 2) == east_area
        # the seat drag: East's own seat barony onto another of East's pips, then outside
        seat = Title.objects.get(seat_domain=east.seat_domain, tier=TitleTier.BARONY)
        seat_area = rung_area_for_title(seat)
        self.web(self.staff, "atlas_carve_footprint", title_id=seat.pk, add=[[2, 3]])
        moved = self.web(self.staff, "atlas_move_seat", title_id=seat.pk, pip=[2, 2])
        assert moved.detail.success, moved.detail.message
        assert holder_at(2, 2) == seat_area
        assert holder_at(2, 3) == east_area
        refused = self.web(self.staff, "atlas_move_seat", title_id=seat.pk, pip=[7, 7])
        assert not refused.detail.success
        assert holder_at(2, 2) == seat_area
        player = self.web(self.player, "atlas_move_seat", title_id=seat.pk, pip=[2, 1])
        assert not player.detail.success
