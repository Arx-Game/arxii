"""Laying out a realm (#4983 slice 2, #4986): staff paste a layout through the web
dispatch, preview it with nothing written, lay it out, read the ladder, and are refused
when they press it twice; a titular line reads Titular on the ladder."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.areas.tests.test_worldmap import tiny_map
from world.areas.worldmap.models import TerrainPip
from world.areas.worldmap.services import create_region_map, import_region_map_file, set_footprint
from world.character_creation.factories import RealmFactory
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.societies.houses.almanach import plant_rung, rung_area_for_title
from world.societies.houses.almanach_reads import ladder_for_realm
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title

LAYOUT = """realm | counties 2 | baronies 1
kingdom Luxen | duchies 3 | seat Lux
kingdom Old Luxen | titular | lore The crown before the revolt.
"""


class LayingOutARealmJourney(JourneyCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        culture = NameCulture.objects.create(name="Luxenne journey", realm=cls.realm)
        names = ("Ashford", "Brackwater", "Coldharbour", "Dunmere", "Eastwold", "Fennick")
        for index, value in enumerate(names):
            NameCultureEntry.objects.create(
                culture=culture, part=NamePart.PLACE, value=value, weight=len(names) - index
            )
        region = create_region_map(name="Catenys", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=region, file_name="t.map", data=tiny_map().encode())
        cls.kingdom = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Luxen")
        outline = sorted(
            (x, y)
            for x, y in TerrainPip.objects.filter(region=region).values_list("x", "y")
            if x < 10
        )
        set_footprint(area=rung_area_for_title(cls.kingdom), add=outline)

    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Map Room")
        self.staff = self.make_player("Apostate", room=room)
        account = self.account_of(self.staff)
        account.is_staff = True
        account.save()
        self.player = self.make_player("Hobb", room=room)

    def test_preview_then_lay_out_then_refused_twice(self) -> None:
        before = Title.objects.count()
        preview = self.web(
            self.staff, "almanach_lay_out", realm_id=self.realm.pk, layout=LAYOUT, commit=False
        )
        assert preview.detail.success, preview.detail.message
        assert preview.detail.data["wrote"] is False
        [luxen, old] = preview.detail.data["kingdoms"]
        assert len(luxen["duchies"]) == 3
        assert old["planted"][TitleTier.KINGDOM] == 1
        assert Title.objects.count() == before

        laid = self.web(
            self.staff, "almanach_lay_out", realm_id=self.realm.pk, layout=LAYOUT, commit=True
        )
        assert laid.detail.success, laid.detail.message
        rows = ladder_for_realm(self.realm).rows
        by_name = {r.name: r for r in rows if r.name}
        assert by_name["Old Luxen"].state == "Titular"
        assert by_name["Lux"].tier == TitleTier.COUNTY
        duchies = [
            r for r in rows if r.tier == TitleTier.DUCHY and r.parent_title_id == self.kingdom.pk
        ]
        assert len(duchies) == 3

        again = self.web(
            self.staff, "almanach_lay_out", realm_id=self.realm.pk, layout=LAYOUT, commit=True
        )
        assert again.detail.success  # the walk ran; each kingdom reports its own refusal
        refusals = [k["refusals"] for k in again.detail.data["kingdoms"]]
        assert any("already has rungs beneath it" in r for r in refusals[0])
        assert any("already on the ladder" in r for r in refusals[1])

        refused = self.web(
            self.player, "almanach_lay_out", realm_id=self.realm.pk, layout=LAYOUT, commit=False
        )
        assert not refused.detail.success
