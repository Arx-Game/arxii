"""Drawing rivers (#5189): staff draw and erase a river through the web dispatch,
an upload of the map file leaves their rivers as they were, and a reset puts back
the rivers the file gives, the river beside an inland kingdom capital among them."""

from __future__ import annotations

from unittest import mock

from integration_tests.harness import JourneyCase
from world.areas.tests.test_worldmap import THREE_RIVERS, tiny_map
from world.areas.worldmap.models import TerrainPip
from world.areas.worldmap.services import (
    create_region_map,
    import_region_map_file,
    set_footprint,
)
from world.character_creation.factories import RealmFactory
from world.societies.houses.almanach import plant_rung, rung_area_for_title
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title

# The tiny map's rivers: a long one down pip column 7, a short one down column 1
# from row 11, and a stream along row 12 that joins the short one. With one major
# river allowed, only the long one is drawn by an upload.
ONE_MAJOR_RIVER = mock.patch("world.areas.worldmap.azgaar.MAJOR_RIVER_COUNT", 1)


def _has_river(x: int, y: int) -> bool:
    return TerrainPip.objects.get(x=x, y=y).has_river


class DrawingRiversJourney(JourneyCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        cls._upload()
        crown = plant_rung(
            realm=RealmFactory(name="Umbros"), tier=TitleTier.KINGDOM, name="The Umbral Empire"
        )
        capital = Title.objects.get(seat_domain=crown.seat_domain, tier=TitleTier.BARONY)
        # the capital stands two pips from the stream and nowhere near water
        set_footprint(area=rung_area_for_title(capital), add=[(4, 14)])

    @classmethod
    def _upload(cls) -> None:
        with ONE_MAJOR_RIVER:
            import_region_map_file(
                region=cls.region, file_name="t.map", data=tiny_map(rivers=THREE_RIVERS).encode()
            )

    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Map Room")
        self.staff = self.make_player("Apostate", room=room)
        account = self.account_of(self.staff)
        account.is_staff = True
        account.save()
        self.player = self.make_player("Hobb", room=room)

    def test_a_drawn_river_survives_an_upload_and_a_reset_puts_the_files_rivers_back(self) -> None:
        region_id = self.region.pk
        assert _has_river(7, 2)  # the upload drew the long river
        assert not _has_river(1, 15)  # and not the short one
        # a player may not draw
        refused = self.web(self.player, "atlas_paint_river", region_id=region_id, pips=[[2, 3]])
        assert not refused.detail.success
        assert not _has_river(2, 3)
        # staff draw a river across two land pips; the sea pip in the stroke is passed over
        drawn = self.web(
            self.staff, "atlas_paint_river", region_id=region_id, pips=[[2, 3], [3, 3], [15, 15]]
        )
        assert drawn.detail.success, drawn.detail.message
        assert drawn.detail.data == {"region_id": region_id, "changed": 2, "river": True}
        assert _has_river(2, 3)
        assert TerrainPip.objects.get(x=2, y=3).terrain == "plain"
        # and erase a pip of the long river
        erased = self.web(
            self.staff, "atlas_paint_river", region_id=region_id, pips=[[7, 2]], river=False
        )
        assert erased.detail.success, erased.detail.message
        assert not _has_river(7, 2)
        # the same file uploaded again leaves every river as staff left it
        self._upload()
        assert _has_river(2, 3)
        assert not _has_river(7, 2)
        assert _has_river(7, 3)
        # a player may not reset
        assert not self.web(self.player, "atlas_reset_rivers", region_id=region_id).detail.success
        assert _has_river(2, 3)
        # a reset puts the file's rivers back: the long river whole, the hand-drawn one
        # gone, and the stream beside the capital kept down to the short river's mouth
        with ONE_MAJOR_RIVER:
            reset = self.web(self.staff, "atlas_reset_rivers", region_id=region_id)
        assert reset.detail.success, reset.detail.message
        assert _has_river(7, 2)
        assert not _has_river(2, 3)
        assert _has_river(4, 12)
        assert _has_river(1, 12)
        assert _has_river(1, 19)
        assert not _has_river(1, 11)  # the short river above where the stream joins it
        assert reset.detail.data["rivers"] == TerrainPip.objects.filter(has_river=True).count()
