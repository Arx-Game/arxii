"""Transient weather: resolution, climate-gated rolling, exposure modifiers, emits (#1522).

Pins the slice-2a invariants: weather resolves most-specific-wins (like climate); the ambient
roll only picks types whose temperature band fits the region's climate (no blizzards in the
tropics); rolling writes decaying source-tagged exposure modifiers that stack with the climate
baseline and feed comfort; and emit selection gates on IC season + time-of-day phase.
"""

from datetime import UTC, datetime

from django.test import TestCase

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.game_clock.constants import Season, TimePhase
from world.game_clock.factories import GameClockFactory
from world.locations.constants import StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import felt_exposure
from world.weather.factories import (
    ClimateFactory,
    RegionWeatherStateFactory,
    WeatherEmitFactory,
    WeatherTypeExposureFactory,
    WeatherTypeFactory,
)
from world.weather.services import (
    clear_region_weather,
    current_conditions,
    eligible_weather_types,
    get_effective_weather,
    roll_region_weather,
    select_weather_emit,
)
from world.weather.tasks import roll_and_echo_weather


class WeatherResolutionTests(TestCase):
    def test_inherited_from_ancestor(self) -> None:
        region = AreaFactory(level=AreaLevel.CITY)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        state = RegionWeatherStateFactory(area=region)
        assert get_effective_weather(ward) == state

    def test_subregion_overrides_parent(self) -> None:
        region = AreaFactory(level=AreaLevel.CITY)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        RegionWeatherStateFactory(area=region)
        ward_state = RegionWeatherStateFactory(area=ward)
        assert get_effective_weather(ward) == ward_state

    def test_none_when_unset(self) -> None:
        assert get_effective_weather(AreaFactory(level=AreaLevel.CITY)) is None
        assert get_effective_weather(None) is None


class WeatherEligibilityTests(TestCase):
    """The ambient roll respects each type's climate temperature band."""

    def test_unbounded_type_is_always_eligible(self) -> None:
        clear = WeatherTypeFactory()
        region = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=50))
        assert clear in eligible_weather_types(region)

    def test_snow_is_filtered_out_of_a_hot_region(self) -> None:
        snow = WeatherTypeFactory(max_temperature=20)  # only cold regions
        hot = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=50))
        cold = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=-40))
        assert snow not in eligible_weather_types(hot)
        assert snow in eligible_weather_types(cold)

    def test_special_weather_is_never_eligible_for_the_ambient_roll(self) -> None:
        eclipse = WeatherTypeFactory(is_automated=False)
        region = AreaFactory(level=AreaLevel.CITY)
        assert eclipse not in eligible_weather_types(region)


class WeatherRollTests(TestCase):
    def _region_room(self, climate=None):
        # Open-air so the room actually feels the weather axes (walls would shelter WET/WIND).
        region = AreaFactory(level=AreaLevel.CITY, climate=climate)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        profile = RoomProfileFactory(area=ward, enclosure=RoomEnclosure.OPEN_AIR)
        return region, profile.objectdb

    def test_roll_writes_decaying_exposure_that_feeds_comfort(self) -> None:
        storm = WeatherTypeFactory(name="Storm")
        WeatherTypeExposureFactory(weather_type=storm, stat_key=StatKey.WET, value=40)
        WeatherTypeExposureFactory(weather_type=storm, stat_key=StatKey.WIND, value=30)
        region, room = self._region_room()

        state = roll_region_weather(region, weather_type=storm)
        assert state is not None
        # The room (open enough to feel weather) feels the storm's WET/WIND.
        assert felt_exposure(room, stat_key=StatKey.WET) == 40
        # Modifiers are source-tagged for cleanup and decay (change_per_day != 0).
        rows = LocationValueModifier.objects.filter(area=region, source=f"weather:{region.pk}")
        assert rows.count() == 2
        assert all(r.change_per_day < 0 for r in rows)

    def test_reroll_replaces_prior_weather_modifiers(self) -> None:
        storm = WeatherTypeFactory()
        WeatherTypeExposureFactory(weather_type=storm, stat_key=StatKey.WET, value=40)
        clear = WeatherTypeFactory()  # no exposures
        region, room = self._region_room()

        roll_region_weather(region, weather_type=storm)
        roll_region_weather(region, weather_type=clear)
        # Storm's WET is gone; clear carries nothing.
        assert felt_exposure(room, stat_key=StatKey.WET) == 0
        assert not LocationValueModifier.objects.filter(source=f"weather:{region.pk}").exists()

    def test_random_roll_only_picks_eligible_types(self) -> None:
        WeatherTypeFactory(name="Snow", max_temperature=20)  # filtered out of a hot region
        sun = WeatherTypeFactory(name="Sun", min_temperature=30)
        hot = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=50))
        state = roll_region_weather(hot)
        assert state is not None
        assert state.weather_type == sun  # only the eligible type can be picked

    def test_roll_returns_none_when_no_eligible_types(self) -> None:
        WeatherTypeFactory(min_temperature=100)  # nothing is this hot
        region = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=0))
        assert roll_region_weather(region) is None

    def test_clear_region_weather_removes_state_and_modifiers(self) -> None:
        storm = WeatherTypeFactory()
        WeatherTypeExposureFactory(weather_type=storm, stat_key=StatKey.WET, value=40)
        region, _ = self._region_room()
        roll_region_weather(region, weather_type=storm)

        clear_region_weather(region)
        assert get_effective_weather(region) is None
        assert not LocationValueModifier.objects.filter(source=f"weather:{region.pk}").exists()


class WeatherEmitTests(TestCase):
    def _clock_at(self, month: int) -> None:
        # Paused clock so season/phase are deterministic. Month picks the season; noon → DAY.
        GameClockFactory(anchor_ic_time=datetime(1010, month, 15, 12, 0, tzinfo=UTC), paused=True)

    def test_emit_gated_by_season_and_phase(self) -> None:
        storm = WeatherTypeFactory()
        # A summer-day emit and a winter-night emit on the same weather.
        WeatherEmitFactory(weather_type=storm, text="summer day", in_summer=True, at_day=True)
        WeatherEmitFactory(weather_type=storm, text="winter night", in_winter=True, at_night=True)
        region = AreaFactory(level=AreaLevel.CITY)
        RegionWeatherStateFactory(area=region, weather_type=storm)
        self._clock_at(7)  # July → summer, noon → day

        emit = select_weather_emit(region)
        assert emit is not None
        assert emit.text == "summer day"

    def test_no_match_returns_none(self) -> None:
        storm = WeatherTypeFactory()
        WeatherEmitFactory(weather_type=storm, text="winter only", in_winter=True, at_day=True)
        region = AreaFactory(level=AreaLevel.CITY)
        RegionWeatherStateFactory(area=region, weather_type=storm)
        self._clock_at(7)  # summer — the winter emit doesn't match
        assert select_weather_emit(region) is None

    def test_explicit_season_phase_override(self) -> None:
        storm = WeatherTypeFactory()
        WeatherEmitFactory(weather_type=storm, text="dusk autumn", in_autumn=True, at_dusk=True)
        region = AreaFactory(level=AreaLevel.CITY)
        RegionWeatherStateFactory(area=region, weather_type=storm)
        emit = select_weather_emit(region, season=Season.AUTUMN, phase=TimePhase.DUSK)
        assert emit is not None
        assert emit.text == "dusk autumn"

    def test_no_weather_returns_none(self) -> None:
        assert select_weather_emit(AreaFactory(level=AreaLevel.CITY)) is None


class CurrentConditionsTests(TestCase):
    def _room(self, *, climate=None, weather_type=None):
        region = AreaFactory(level=AreaLevel.CITY, climate=climate)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        profile = RoomProfileFactory(area=ward)
        if weather_type is not None:
            RegionWeatherStateFactory(area=region, weather_type=weather_type)
        return profile.objectdb

    def _summer_noon_clock(self) -> None:
        GameClockFactory(anchor_ic_time=datetime(1010, 7, 15, 12, 0, tzinfo=UTC), paused=True)

    def test_no_clock_no_weather_is_all_none(self) -> None:
        conditions = current_conditions(self._room())
        assert conditions.ic_time is None
        assert conditions.weather_type is None
        assert conditions.emit_text is None

    def test_reports_time_and_weather_with_emit(self) -> None:
        self._summer_noon_clock()
        storm = WeatherTypeFactory(name="Storm")
        WeatherEmitFactory(weather_type=storm, text="rain lashes down", in_summer=True, at_day=True)
        conditions = current_conditions(self._room(weather_type=storm))
        assert conditions.ic_time is not None
        assert conditions.season == Season.SUMMER
        assert conditions.phase == TimePhase.DAY
        assert conditions.weather_type == storm
        assert conditions.emit_text == "rain lashes down"

    def test_weather_without_a_matching_emit_omits_the_line(self) -> None:
        self._summer_noon_clock()
        storm = WeatherTypeFactory()  # no emits at all
        conditions = current_conditions(self._room(weather_type=storm))
        assert conditions.weather_type == storm
        assert conditions.emit_text is None


class WeatherTickTests(TestCase):
    def test_rolls_climate_regions_and_skips_climateless(self) -> None:
        WeatherTypeFactory()  # one unbounded automated type, eligible anywhere
        region = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=10))
        climateless = AreaFactory(level=AreaLevel.CITY)
        roll_and_echo_weather()
        assert get_effective_weather(region) is not None
        assert get_effective_weather(climateless) is None

    def test_tick_is_safe_with_no_eligible_weather(self) -> None:
        AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory())  # no weather types exist
        roll_and_echo_weather()  # must not raise
