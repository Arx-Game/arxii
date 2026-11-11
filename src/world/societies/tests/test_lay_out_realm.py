"""Laying out a realm (#4983 slice 2, #4986): the walk that plants a drawn kingdom's
ladder from a layout, counties first and duchies as groups of them (#5029), and the
refusals that keep a typo from planting twice."""

from __future__ import annotations

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.tests.test_worldmap import tiny_map
from world.areas.worldmap.constants import Terrain
from world.areas.worldmap.models import TerrainPip
from world.areas.worldmap.services import (
    create_region_map,
    footprint_of,
    import_region_map_file,
    set_footprint,
)
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import chartered_extent, plant_rung, rung_area_for_title
from world.societies.houses.constants import TitleStation, TitleTier
from world.societies.houses.layout import (
    LayoutRefused,
    lay_out_realm,
    parse_layout,
    preview_layout,
)
from world.societies.houses.models import Domain, FealtyEdge, Title, TitleClaim

PLACE_NAMES = [
    "Ashford",
    "Brackwater",
    "Coldharbour",
    "Dunmere",
    "Eastwold",
    "Fennick",
    "Greyhaven",
    "Hollowdene",
    "Ironcross",
    "Juniper Vale",
    "Kingsreach",
    "Lowmoor",
]


REGIONAL_NAMES = [
    "Carradyn",
    "Penmora",
    "Aberwen",
    "Tregarion",
    "Maelor",
    "Brynmar",
    "Dynmere",
    "Carvenna",
]


class LayOutRealmTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Luxen")
        culture = NameCulture.objects.create(name="Luxenne test", realm=cls.realm)
        for index, value in enumerate(PLACE_NAMES):
            NameCultureEntry.objects.create(
                culture=culture, part=NamePart.PLACE, value=value, weight=len(PLACE_NAMES) - index
            )
        # a regional culture carries no realm link: only a kingdom line's `names` word reaches it
        regional = NameCulture.objects.create(name="Vestyr test")
        for index, value in enumerate(REGIONAL_NAMES):
            NameCultureEntry.objects.create(
                culture=regional,
                part=NamePart.PLACE,
                value=value,
                weight=len(REGIONAL_NAMES) - index,
            )
        NameCulture.objects.create(name="Empty test")
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=cls.region, file_name="t.map", data=tiny_map().encode())
        cls.kingdom = plant_rung(realm=cls.realm, tier=TitleTier.KINGDOM, name="Luxen")
        # the kingdom's outline: the map's land half, lake included, as the owner draws it
        cls.outline = {
            (x, y)
            for x, y, terrain in TerrainPip.objects.filter(region=cls.region).values_list(
                "x", "y", "terrain"
            )
            if x < 10
        }
        cls.water = {
            (x, y)
            for x, y, terrain in TerrainPip.objects.filter(region=cls.region).values_list(
                "x", "y", "terrain"
            )
            if x < 10 and terrain in (Terrain.WATER, Terrain.LAKE)
        }
        set_footprint(area=rung_area_for_title(cls.kingdom), add=sorted(cls.outline))

    def test_preview_counts_and_writes_nothing(self) -> None:
        before = Title.objects.count()
        layout = parse_layout("realm | counties 2 | baronies 1\nkingdom Luxen | duchies 3\n")
        report = preview_layout(self.realm, layout)
        assert not report.wrote
        assert Title.objects.count() == before
        assert report.refusals == []
        [kingdom] = report.kingdoms
        assert kingdom.name == "Luxen"
        assert len(kingdom.duchies) == 3
        assert sum(d["pips"] for d in kingdom.duchies) == len(self.outline)
        assert kingdom.duchies[0]["capital"] is True
        assert kingdom.planted[TitleTier.DUCHY] == 2  # the crown's own chain duchy exists already
        # counties 2 per duchy; the capital duchy takes capital x1.5 of them, so 3 (#5029)
        assert kingdom.planted[TitleTier.COUNTY] == 3 + 2 + 2 - 1
        assert len(kingdom.names) == 3 + 7  # every duchy and county takes a name from the bank
        sizes = [d["pips"] for d in kingdom.duchies]
        assert sizes[0] > max(sizes[1:]), sizes

    def test_lay_out_plants_contiguous_duchies_with_the_capital_largest(self) -> None:
        layout = parse_layout(
            "realm | counties 2 | baronies 2 | capital x2\nkingdom Luxen | duchies 3 | seat Lux\n"
        )
        report = lay_out_realm(self.realm, layout)
        assert report.wrote
        assert report.refusals == []
        duchies = list(Title.objects.filter(realm=self.realm, tier=TitleTier.DUCHY).order_by("pk"))
        assert len(duchies) == 3
        footprints = [footprint_of(rung_area_for_title(d)) for d in duchies]
        assert set().union(*footprints) == self.outline
        assert sum(len(f) for f in footprints) == len(self.outline)
        chain_duchy = Title.objects.get(seat_domain=self.kingdom.seat_domain, tier=TitleTier.DUCHY)
        capital_pips = footprint_of(rung_area_for_title(chain_duchy))
        assert len(capital_pips) == max(len(f) for f in footprints)
        seat_county = Title.objects.get(seat_domain=self.kingdom.seat_domain, tier=TitleTier.COUNTY)
        assert seat_county.name == "Lux"
        counties = Title.objects.filter(realm=self.realm, tier=TitleTier.COUNTY)
        # the capital duchy takes capital x2 of the two counties, so 4 + 2 + 2 (#5029)
        assert counties.count() == 8
        land = self.outline - self.water
        county_sizes = [len(footprint_of(rung_area_for_title(c)) & land) for c in counties]
        assert max(county_sizes) <= 2 * min(county_sizes), county_sizes
        for county in counties:
            county_pips = footprint_of(rung_area_for_title(county))
            seat_barony = Title.objects.get(seat_domain=county.seat_domain, tier=TitleTier.BARONY)
            assert len(footprint_of(rung_area_for_title(seat_barony))) == 1
            domain = Domain.objects.get(pk=rung_area_for_title(county).pk)
            assert domain.population == 120 * len(county_pips)
            assert domain.description.startswith("PLACEHOLDER:") or county == seat_county
        baronies = Title.objects.filter(realm=self.realm, tier=TitleTier.BARONY)
        assert baronies.count() == 16  # a seat barony and one more per county
        # A duchy is its counties (#5069): no Domain above county, so the capital rule
        # shows on the counties and a duchy's figure prose lives on its Area.
        assert not Domain.objects.filter(area__level__gt=AreaLevel.COUNTY).exists()
        assert Domain.objects.get(pk=rung_area_for_title(seat_county).pk).prosperity == 65
        other = next(d for d in duchies if d.pk != chain_duchy.pk)
        other_county = next(
            c for c in counties if rung_area_for_title(c).parent_id == rung_area_for_title(other).pk
        )
        assert Domain.objects.get(pk=rung_area_for_title(other_county).pk).prosperity == 45
        assert rung_area_for_title(other).description.startswith("PLACEHOLDER:")
        assert other.name in PLACE_NAMES
        names = [t.name for t in Title.objects.filter(realm=self.realm) if t.name]
        assert len(names) == len(set(names)), names

    def test_a_second_lay_out_is_refused_whole(self) -> None:
        layout = parse_layout("kingdom Luxen | duchies 2\n")
        lay_out_realm(self.realm, layout)
        before = Title.objects.count()
        report = lay_out_realm(self.realm, layout)
        [kingdom] = report.kingdoms
        assert any("already has rungs beneath it" in r for r in kingdom.refusals)
        assert Title.objects.count() == before

    def test_titular_line_plants_a_landless_crown_with_its_charter(self) -> None:
        first = lay_out_realm(self.realm, parse_layout("kingdom Luxen | duchies 2\n"))
        a, b = (d["name"] for d in first.kingdoms[0].duchies)
        layout = parse_layout(
            f"kingdom Old Luxen | titular | chartered {a}, {b}"
            " | lore The crown before the revolt.\n"
        )
        report = lay_out_realm(self.realm, layout)
        assert report.refusals == []
        assert all(k.refusals == [] for k in report.kingdoms)
        old = Title.objects.get(name="Old Luxen")
        assert old.station == TitleStation.TITULAR
        assert not old.is_claimable
        assert footprint_of(rung_area_for_title(old)) == set()
        fiefs = Title.objects.filter(name__in=[a, b], tier=TitleTier.DUCHY)
        assert fiefs.count() == 2
        assert chartered_extent(old) == set().union(
            *(footprint_of(rung_area_for_title(f)) for f in fiefs)
        )
        # a titular crown has no Domain; its lore lives on its own Area (#5069)
        assert rung_area_for_title(old).description == "The crown before the revolt."
        # the same titular line again is refused by name
        again = lay_out_realm(self.realm, parse_layout("kingdom Old Luxen | titular\n"))
        assert any("already on the ladder" in r for r in again.kingdoms[0].refusals)

    def test_sworn_pledges_a_crown_in_another_realm_and_claimed_by_records_a_claim(self) -> None:
        umbros = RealmFactory(name="Umbros")
        throne = OrganizationFactory(name="The Umbral Throne")
        plant_rung(realm=umbros, tier=TitleTier.EMPIRE, name="The Umbral Empire", held_by=throne)
        sharlotte = CharacterSheetFactory()
        sharlotte.character.key = "Sharlotte"
        sharlotte.character.save()
        layout = parse_layout(
            "kingdom Luxen | duchies 2 | claimed by Sharlotte | basis The exiled queen\n"
            "  duchy Brittany | sworn The Umbral Empire | held\n"
        )
        report = lay_out_realm(self.realm, layout)
        assert all(k.refusals == [] for k in report.kingdoms), report.kingdoms[0].refusals
        brittany = Title.objects.get(name="Brittany")
        assert brittany.pledged_liege.name == "The Umbral Empire"
        assert not brittany.is_claimable
        claim = TitleClaim.objects.get(title=self.kingdom)
        assert claim.claimant == sharlotte
        assert claim.basis == "The exiled queen"
        assert not FealtyEdge.objects.filter(vassal__name="House Brittany").exists()

    def test_the_bank_runs_dry_into_undefined_rungs(self) -> None:
        layout = parse_layout("realm | counties 4 | baronies 1\nkingdom Luxen | duchies 5\n")
        report = lay_out_realm(self.realm, layout)
        assert report.kingdoms[0].refusals == []
        named = [t for t in Title.objects.filter(realm=self.realm) if t.name]
        unnamed = Title.objects.filter(realm=self.realm, name="")
        names = [t.name for t in named]
        assert len(names) == len(set(names))
        assert unnamed.filter(tier__in=(TitleTier.DUCHY, TitleTier.COUNTY)).exists()

    def test_generated_duchies_are_claimable_only_when_the_layout_says_so(self) -> None:
        layout = parse_layout(
            "kingdom Luxen | duchies 4\n  duchy Brittany | claimable\n  duchy Anjou | held\n"
        )
        report = lay_out_realm(self.realm, layout)
        assert report.kingdoms[0].refusals == []
        assert Title.objects.get(name="Brittany").is_claimable
        assert not Title.objects.get(name="Anjou").is_claimable
        chain_duchy = Title.objects.get(seat_domain=self.kingdom.seat_domain, tier=TitleTier.DUCHY)
        generated = (
            Title.objects.filter(realm=self.realm, tier=TitleTier.DUCHY)
            .exclude(name__in=["Brittany", "Anjou"])
            .exclude(pk=chain_duchy.pk)
        )
        assert generated.count() == 1
        assert not generated.first().is_claimable

    def test_names_already_borne_anywhere_are_refused_at_preview(self) -> None:
        elsewhere = RealmFactory(name="Umbros")
        plant_rung(realm=elsewhere, tier=TitleTier.DUCHY, name="Brittany")
        report = preview_layout(
            self.realm,
            parse_layout("kingdom Luxen | duchies 2\n  duchy Brittany\n  duchy Anjou\n"),
        )
        [kingdom] = report.kingdoms
        assert any(r.startswith("line 2:") and "Brittany" in r for r in kingdom.refusals)
        twice = preview_layout(
            self.realm, parse_layout("kingdom Luxen | duchies 3\n  duchy Anjou\n  duchy Anjou\n")
        )
        assert any("line 3:" in r and "Anjou" in r for r in twice.kingdoms[0].refusals)
        # a chartered name that matches nothing is refused at preview, not at lay-out
        charter = preview_layout(
            self.realm, parse_layout("kingdom Old Luxen | titular | chartered Nowhere\n")
        )
        assert any("Nowhere" in r for r in charter.kingdoms[0].refusals)

    def test_names_are_drawn_heaviest_first(self) -> None:
        layout = parse_layout("realm | counties 1 | baronies 1\nkingdom Luxen | duchies 2\n")
        report = preview_layout(self.realm, layout)
        # weights descend down PLACE_NAMES; two duchies and three counties (the capital
        # duchy takes x1.5 of one, rounded up) take the top five
        assert set(report.kingdoms[0].names) == set(PLACE_NAMES[:5])

    def test_names_word_draws_only_from_that_culture_and_a_plain_line_never_does(self) -> None:
        layout = parse_layout(
            "realm | counties 1 | baronies 1\n"
            "kingdom Luxen | duchies 2\n"
            "kingdom Old Luxen | titular | names vestyr TEST\n  duchy\n  duchy\n"
        )
        report = preview_layout(self.realm, layout)
        assert report.refusals == []
        plain, regional = report.kingdoms
        assert plain.names
        assert set(plain.names) <= set(PLACE_NAMES)
        assert len(regional.names) == 2
        assert set(regional.names) <= set(REGIONAL_NAMES)

    def test_an_unknown_culture_or_one_with_no_place_names_refuses_that_kingdom_only(self) -> None:
        for culture, fragment in (("Nowhere", "no place-name culture"), ("Empty test", "no place")):
            report = preview_layout(
                self.realm,
                parse_layout(f"kingdom Luxen | duchies 2 | names {culture}\nkingdom | potential\n"),
            )
            [refusal] = report.refusals
            assert refusal.startswith("line 1:"), refusal
            assert culture in refusal, refusal
            assert fragment in refusal, refusal
            assert report.kingdoms[1].refusals == []

    def test_every_kingdom_naming_a_culture_needs_no_realm_bank(self) -> None:
        bare = RealmFactory(name="Arvum")
        report = preview_layout(bare, parse_layout("kingdom | potential | names Vestyr test\n"))
        assert report.refusals == []
        with self.assertRaises(LayoutRefused):
            preview_layout(
                bare, parse_layout("kingdom | potential | names Vestyr test\nkingdom | potential\n")
            )

    def test_no_place_bank_refuses_the_realm(self) -> None:
        bare = RealmFactory(name="Arvum")
        with self.assertRaises(LayoutRefused) as caught:
            preview_layout(bare, parse_layout("kingdom | potential\n"))
        assert "place-name bank" in caught.exception.user_message

    def test_errors_name_the_line(self) -> None:
        report = preview_layout(
            self.realm,
            parse_layout("kingdom Nowhere | duchies 2\nkingdom Luxen | duchies 2 | sworn Nobody\n"),
        )
        assert any(
            r.startswith("line 1:") and "no kingdom named Nowhere" in r for r in report.refusals
        )
        assert any(r.startswith("line 2:") and "Nobody" in r for r in report.refusals)
