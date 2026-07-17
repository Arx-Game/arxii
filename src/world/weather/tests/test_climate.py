"""Climate resolution, the per-month temperature curve, and the exposure decomposition (#1522).

Pins the design invariants: climate resolves most-specific-wins up the area hierarchy (like
realm); the signed temperature/moisture weights decompose onto the floored COLD/HEAT/WET/DRY
axes (a signed weight feeds exactly one of its pair); the global per-month shift rides on top
of temperature; and WIND is never climate-driven.
"""

from datetime import UTC, datetime

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.game_clock.factories import GameClockFactory
from world.locations.constants import StatKey
from world.weather.constants import MONTH_TEMPERATURE_SHIFT
from world.weather.factories import ClimateFactory
from world.weather.models import Climate
from world.weather.services import (
    climate_exposure_base,
    current_temperature_shift,
    get_effective_climate,
    month_temperature_shift,
)


class ClimateResolutionTests(TestCase):
    """get_effective_climate walks up the hierarchy, most-specific-wins (mirrors realm)."""

    def test_direct_assignment(self) -> None:
        tropical = ClimateFactory(temperature=40, moisture=40)
        region = AreaFactory(level=AreaLevel.CITY, climate=tropical)
        assert get_effective_climate(region) == tropical

    def test_inherited_from_ancestor(self) -> None:
        desert = ClimateFactory(temperature=45, moisture=-45)
        region = AreaFactory(level=AreaLevel.CITY, climate=desert)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        assert get_effective_climate(ward) == desert

    def test_subregion_overrides_parent(self) -> None:
        # Luxen (temperate) with a desert sub-region: the room resolves the nearest climate.
        temperate = ClimateFactory(temperature=0, moisture=0)
        desert = ClimateFactory(temperature=45, moisture=-45)
        luxen = AreaFactory(level=AreaLevel.CITY, climate=temperate)
        cinderus = AreaFactory(level=AreaLevel.WARD, parent=luxen, climate=desert)
        assert get_effective_climate(cinderus) == desert
        assert get_effective_climate(luxen) == temperate

    def test_none_when_unset(self) -> None:
        region = AreaFactory(level=AreaLevel.CITY)
        assert get_effective_climate(region) is None
        assert get_effective_climate(None) is None


class ExposureDecompositionTests(TestCase):
    """Signed weights decompose onto the floored axes; a weight feeds exactly one of its pair."""

    def test_hot_climate_feeds_heat_not_cold(self) -> None:
        climate = ClimateFactory(temperature=50, moisture=0)
        assert climate_exposure_base(climate, StatKey.HEAT) == 50
        assert climate_exposure_base(climate, StatKey.COLD) == 0

    def test_cold_climate_feeds_cold_not_heat(self) -> None:
        climate = ClimateFactory(temperature=-50, moisture=0)
        assert climate_exposure_base(climate, StatKey.COLD) == 50
        assert climate_exposure_base(climate, StatKey.HEAT) == 0

    def test_wet_and_dry_split_on_moisture_sign(self) -> None:
        wet = ClimateFactory(temperature=0, moisture=40)
        dry = ClimateFactory(temperature=0, moisture=-40)
        assert climate_exposure_base(wet, StatKey.WET) == 40
        assert climate_exposure_base(wet, StatKey.DRY) == 0
        assert climate_exposure_base(dry, StatKey.DRY) == 40
        assert climate_exposure_base(dry, StatKey.WET) == 0

    def test_wind_is_never_climate_driven(self) -> None:
        climate = ClimateFactory(temperature=50, moisture=50)
        assert climate_exposure_base(climate, StatKey.WIND) == 0

    def test_none_climate_is_zero(self) -> None:
        assert climate_exposure_base(None, StatKey.HEAT) == 0

    def test_seasonal_shift_pushes_temperature(self) -> None:
        # A temperate region in deep winter (shift -50) crosses into real COLD;
        # a hot region's high baseline (+60) still nets warm under the same shift ("no winter").
        temperate = ClimateFactory(temperature=0, moisture=0)
        tropical = ClimateFactory(temperature=60, moisture=40)
        assert climate_exposure_base(temperate, StatKey.COLD, temperature_shift=-50) == 50
        assert climate_exposure_base(temperate, StatKey.HEAT, temperature_shift=-50) == 0
        assert climate_exposure_base(tropical, StatKey.COLD, temperature_shift=-50) == 0
        assert climate_exposure_base(tropical, StatKey.HEAT, temperature_shift=-50) == 10


class SeasonalShiftTests(TestCase):
    """The per-month curve is read off the IC clock; absent a clock the shift is simply 0."""

    def test_month_lookup(self) -> None:
        assert month_temperature_shift(1) == MONTH_TEMPERATURE_SHIFT[1]
        assert month_temperature_shift(7) == MONTH_TEMPERATURE_SHIFT[7]
        assert month_temperature_shift(99) == 0

    def test_no_clock_means_no_shift(self) -> None:
        assert current_temperature_shift() == 0

    def test_reads_ic_month_from_clock(self) -> None:
        # Paused clock anchored in January → the January shift (coldest).
        january = datetime(1010, 1, 15, 12, 0, tzinfo=UTC)
        GameClockFactory(anchor_ic_time=january, paused=True)
        assert current_temperature_shift() == MONTH_TEMPERATURE_SHIFT[1]


class ClimateNaturalKeyTests(TestCase):
    """Climate carries a name natural key (#2448), like WeatherType."""

    def test_get_by_natural_key(self) -> None:
        climate = Climate.objects.create(name="Temperate-Test")
        assert Climate.objects.get_by_natural_key("Temperate-Test").pk == climate.pk
