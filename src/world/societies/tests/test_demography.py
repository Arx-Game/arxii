"""Demography (#5069 slice 1, #5071): population is a formula, not a tick; terrain sets
a holding's capacity; a noble's land income follows its people."""

from datetime import timedelta
import math

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.worldmap.constants import PipSource, Terrain
from world.areas.worldmap.models import AreaFootprintPip, RegionMap, TerrainPip
from world.areas.worldmap.services import create_region_map, set_footprint
from world.game_clock.factories import GameClockFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.demography import (
    population_now,
    prosperity_modifier_for,
    refresh_terrain_counts,
    set_capacity_override,
)
from world.societies.houses.models import DomainTerrainCount, DominionConfig, TerrainCalibration
from world.societies.houses.services import create_domain
from world.societies.territory import ensure_domain_stream, territory_gross

YEAR = timedelta(days=360)


def _config(**values) -> DominionConfig:
    config = DominionConfig.load()
    for name, value in values.items():
        setattr(config, name, value)
    config.save()
    return config


class PopulationFormulaTests(TestCase):
    """``population_now`` is the base as of ``population_rebased_at`` moved toward
    capacity by the elapsed in-character months; nothing is written."""

    def setUp(self):
        self.rebased_at = timezone.now() - YEAR
        GameClockFactory(anchor_real_time=self.rebased_at, time_ratio=1.0)
        _config(population_rate_pct_per_month=10)
        self.county = AreaFactory(level=AreaLevel.COUNTY)
        self.domain = create_domain(
            area=self.county, name="Vale", owner_org=OrganizationFactory(name="House Vale")
        )
        self.domain.population_rebased_at = self.rebased_at
        self.domain.save(update_fields=["population_rebased_at"])

    def _set(self, *, population: int, capacity: int) -> None:
        self.domain.population = population
        self.domain.population_capacity = capacity
        self.domain.save(update_fields=["population", "population_capacity"])

    def test_population_grows_toward_capacity(self):
        self._set(population=500, capacity=1000)

        now = population_now(self.domain, at=self.rebased_at + YEAR)

        # twelve months at ten percent: the gap closes by 1 - e^-1.2
        self.assertEqual(now, round(1000 - 500 * math.exp(-1.2)))
        self.domain.refresh_from_db()
        self.assertEqual(self.domain.population, 500, "a read never writes")

    def test_population_above_capacity_falls_toward_it(self):
        self._set(population=2000, capacity=1000)

        self.assertEqual(
            population_now(self.domain, at=self.rebased_at + YEAR),
            round(1000 + 1000 * math.exp(-1.2)),
        )

    def test_a_holding_with_no_capacity_empties(self):
        self._set(population=500, capacity=0)

        self.assertEqual(
            population_now(self.domain, at=self.rebased_at + YEAR), round(500 * math.exp(-1.2))
        )

    def test_no_elapsed_time_reads_the_base(self):
        self._set(population=500, capacity=1000)

        self.assertEqual(population_now(self.domain, at=self.rebased_at), 500)


class PopulationWithoutAClockTests(TestCase):
    def test_no_clock_means_no_time_passes(self):
        domain = create_domain(
            area=AreaFactory(level=AreaLevel.COUNTY),
            name="Still",
            owner_org=OrganizationFactory(name="House Still"),
        )
        domain.population = 500
        domain.population_capacity = 1000
        domain.population_rebased_at = timezone.now() - YEAR
        domain.save(update_fields=["population", "population_capacity", "population_rebased_at"])

        self.assertEqual(population_now(domain), 500)


class TerrainCapacityTests(TestCase):
    """A county's capacity is the sum over its own footprint pips of the terrain's
    calibration; a barony's is its one pip times the barony factor."""

    def setUp(self):
        _config(barony_capacity_factor=50)
        TerrainCalibration.objects.create(terrain=Terrain.PLAIN, capacity_per_pip=100)
        TerrainCalibration.objects.create(terrain=Terrain.HILL, capacity_per_pip=40)
        self.region = RegionMap.objects.create(
            name="Test", anchor_x=0, anchor_y=0, width_cells=1, height_cells=1
        )
        self.county = AreaFactory(level=AreaLevel.COUNTY)
        self.barony = AreaFactory(level=AreaLevel.BARONY, parent=self.county)
        house = OrganizationFactory(name="House Vale")
        self.county_domain = create_domain(area=self.county, name="Vale", owner_org=house)
        self.barony_domain = create_domain(area=self.barony, name="Valehold", owner_org=house)
        terrain = {
            (0, 0): Terrain.PLAIN,
            (1, 0): Terrain.PLAIN,
            (2, 0): Terrain.PLAIN,
            (0, 1): Terrain.HILL,
            (1, 1): Terrain.HILL,
            (2, 1): Terrain.FOREST,
            (3, 1): Terrain.PLAIN,
        }
        for (x, y), kind in terrain.items():
            TerrainPip.objects.create(
                region=self.region, x=x, y=y, terrain=kind, source=PipSource.GENERATOR
            )
        # The barony's seat pip is the barony's row; the rest are the county's own.
        AreaFootprintPip.objects.create(area=self.barony, x=3, y=1)
        for x, y in [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]:
            AreaFootprintPip.objects.create(area=self.county, x=x, y=y)

    def test_the_county_counts_its_own_pips_and_sums_their_capacity(self):
        capacity = refresh_terrain_counts(self.county)

        self.assertEqual(capacity, 3 * 100 + 2 * 40)
        counts = dict(
            DomainTerrainCount.objects.filter(domain=self.county_domain).values_list(
                "terrain", "pips"
            )
        )
        self.assertEqual(counts, {Terrain.PLAIN: 3, Terrain.HILL: 2, Terrain.FOREST: 1})
        self.county_domain.refresh_from_db()
        self.assertEqual(self.county_domain.population_capacity, 380)

    def test_a_terrain_with_no_calibration_feeds_nobody(self):
        refresh_terrain_counts(self.county)

        self.county_domain.refresh_from_db()
        # the forest pip is counted but adds nothing until a calibration row says what it feeds
        self.assertEqual(self.county_domain.population_capacity, 380)

    def test_a_barony_is_its_one_pip_times_the_barony_factor(self):
        capacity = refresh_terrain_counts(self.barony)

        self.assertEqual(capacity, 100 * 50)
        self.barony_domain.refresh_from_db()
        self.assertEqual(self.barony_domain.population_capacity, 5000)

    def test_a_refresh_replaces_stale_counts(self):
        refresh_terrain_counts(self.county)
        AreaFootprintPip.objects.filter(area=self.county, y=1).delete()

        refresh_terrain_counts(self.county)

        counts = dict(
            DomainTerrainCount.objects.filter(domain=self.county_domain).values_list(
                "terrain", "pips"
            )
        )
        self.assertEqual(counts, {Terrain.PLAIN: 3})

    def test_an_area_with_no_domain_is_left_alone(self):
        duchy = AreaFactory(level=AreaLevel.DUCHY)

        self.assertEqual(refresh_terrain_counts(duchy), 0)
        self.assertFalse(DomainTerrainCount.objects.filter(domain__area=duchy).exists())

    def test_a_staff_override_stands_in_for_the_terrain_until_cleared(self):
        # A capital and a border fort sit on the same ground (#5069 slice 2).
        set_capacity_override(self.barony_domain, 300000)
        self.barony_domain.refresh_from_db()
        self.assertEqual(self.barony_domain.population_capacity, 300000)
        refresh_terrain_counts(self.barony)
        self.barony_domain.refresh_from_db()
        self.assertEqual(self.barony_domain.population_capacity, 300000, "a carve keeps it")

        set_capacity_override(self.barony_domain, None)

        self.barony_domain.refresh_from_db()
        self.assertEqual(self.barony_domain.population_capacity, 100 * 50)

    def test_the_terrains_pull_on_prosperity_is_the_pip_weighted_modifier(self):
        for terrain, modifier in ((Terrain.PLAIN, 10), (Terrain.HILL, -4)):
            row = TerrainCalibration.objects.get(terrain=terrain)
            row.prosperity_modifier = modifier
            row.save(update_fields=["prosperity_modifier"])
        refresh_terrain_counts(self.county)

        # 3 plain at +10, 2 hill at -4, 1 forest with no row: 22 over 6 pips
        self.assertEqual(prosperity_modifier_for(self.county_domain), round(22 / 6))


class CarveRecountsTests(TestCase):
    """A carve is where a footprint changes, so it is where the terrain is recounted
    (#5069 tick budget: pips never tick; counts are written where the ground moves)."""

    def setUp(self):
        _config(barony_capacity_factor=10)
        TerrainCalibration.objects.create(terrain=Terrain.PLAIN, capacity_per_pip=100)
        TerrainCalibration.objects.create(terrain=Terrain.HILL, capacity_per_pip=40)
        self.region = create_region_map(name="Carveland", anchor_x=0, anchor_y=0, width_cells=1)
        for (x, y), kind in {
            (0, 0): Terrain.PLAIN,
            (1, 0): Terrain.PLAIN,
            (0, 1): Terrain.HILL,
            (1, 1): Terrain.HILL,
        }.items():
            TerrainPip.objects.create(
                region=self.region, x=x, y=y, terrain=kind, source=PipSource.GENERATOR
            )
        self.county = AreaFactory(level=AreaLevel.COUNTY)
        self.barony = AreaFactory(level=AreaLevel.BARONY, parent=self.county)
        house = OrganizationFactory(name="House Carve")
        self.county_domain = create_domain(area=self.county, name="Carve", owner_org=house)
        self.barony_domain = create_domain(area=self.barony, name="Carvehold", owner_org=house)

    def test_growing_a_county_recounts_it(self):
        set_footprint(area=self.county, add=[(0, 0), (1, 0), (0, 1)])

        self.county_domain.refresh_from_db()
        self.assertEqual(self.county_domain.population_capacity, 2 * 100 + 40)

    def test_carving_a_barony_moves_the_pip_and_recounts_both(self):
        set_footprint(area=self.county, add=[(0, 0), (1, 0), (0, 1)])

        set_footprint(area=self.barony, add=[(1, 0)])

        self.county_domain.refresh_from_db()
        self.barony_domain.refresh_from_db()
        self.assertEqual(self.county_domain.population_capacity, 100 + 40)
        self.assertEqual(self.barony_domain.population_capacity, 100 * 10)

    def test_shrinking_a_barony_hands_the_pip_back_and_recounts_both(self):
        set_footprint(area=self.county, add=[(0, 0), (1, 0), (0, 1)])
        set_footprint(area=self.barony, add=[(1, 0)])

        set_footprint(area=self.barony, remove=[(1, 0)])

        self.county_domain.refresh_from_db()
        self.barony_domain.refresh_from_db()
        self.assertEqual(self.county_domain.population_capacity, 2 * 100 + 40)
        self.assertEqual(self.barony_domain.population_capacity, 0)


class IncomeByPeopleTests(TestCase):
    """``territory_gross`` for a Domain is its people times coppers per head times the
    prosperity multiplier; the rooms under it no longer count (ADR-0319 amended)."""

    def test_gross_follows_people_not_rooms(self):
        _config(coppers_per_head=1)
        county = AreaFactory(level=AreaLevel.COUNTY)
        RoomProfileFactory(area=county, is_outdoor=True)
        RoomProfileFactory(area=county, is_outdoor=True)
        domain = create_domain(
            area=county, name="Vale", owner_org=OrganizationFactory(name="House Vale")
        )
        domain.population = 1000
        domain.population_capacity = 1000
        domain.prosperity = 100
        domain.save(update_fields=["population", "population_capacity", "prosperity"])
        stream = ensure_domain_stream(domain)

        self.assertEqual(territory_gross(stream), 1000 * 1 * 2)
