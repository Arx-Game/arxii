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
    FeastDayFactory,
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
    special_weather_for_today,
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


class FeastDayWeatherTests(TestCase):
    def _clock_on(self, month: int, day: int) -> None:
        GameClockFactory(anchor_ic_time=datetime(1010, month, day, 12, 0, tzinfo=UTC), paused=True)

    def test_special_weather_matches_feast_date(self) -> None:
        eclipse = WeatherTypeFactory(name="Eclipse", is_automated=False)
        FeastDayFactory(name="Mirror Eclipse", ic_month=10, ic_day=31, weather_type=eclipse)
        self._clock_on(10, 31)
        assert special_weather_for_today() == eclipse

    def test_no_special_weather_on_an_ordinary_day(self) -> None:
        eclipse = WeatherTypeFactory(is_automated=False)
        FeastDayFactory(ic_month=10, ic_day=31, weather_type=eclipse)
        self._clock_on(11, 1)
        assert special_weather_for_today() is None

    def test_inactive_feast_day_is_ignored(self) -> None:
        eclipse = WeatherTypeFactory(is_automated=False)
        FeastDayFactory(ic_month=10, ic_day=31, weather_type=eclipse, is_active=False)
        self._clock_on(10, 31)
        assert special_weather_for_today() is None

    def test_no_clock_means_no_special_weather(self) -> None:
        eclipse = WeatherTypeFactory(is_automated=False)
        FeastDayFactory(ic_month=10, ic_day=31, weather_type=eclipse)
        assert special_weather_for_today() is None

    def test_tick_forces_special_weather_world_wide_on_a_feast_day(self) -> None:
        # A special (non-automated, normally never-rolled) type is forced over a climate region.
        madness = WeatherTypeFactory(name="Moon Madness", is_automated=False)
        WeatherTypeFactory(name="Clear")  # the normal type that would otherwise roll
        FeastDayFactory(ic_month=10, ic_day=31, weather_type=madness)
        region = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory(temperature=10))
        self._clock_on(10, 31)

        roll_and_echo_weather()
        state = get_effective_weather(region)
        assert state is not None
        assert state.weather_type == madness


class WeatherShelterTests(TestCase):
    """#2845/ADR-0180: cloud cover materializes as area-wide hazard shelter."""

    def setUp(self):
        from world.conditions.factories import ensure_radiant_damage_type

        self.radiant = ensure_radiant_damage_type()
        self.region = AreaFactory(level=AreaLevel.CITY, climate=ClimateFactory())
        self.overcast = WeatherTypeFactory(name="Overcast")
        from world.weather.factories import WeatherTypeShelterFactory

        WeatherTypeShelterFactory(weather_type=self.overcast, damage_type=self.radiant, value=6)

    def test_roll_materializes_damage_type_shelter_modifier(self):
        from world.locations.constants import KeyType
        from world.locations.models import LocationValueModifier

        roll_region_weather(self.region, weather_type=self.overcast)
        row = LocationValueModifier.objects.get(area=self.region, key_type=KeyType.DAMAGE_TYPE)
        self.assertEqual(row.damage_type, self.radiant)
        self.assertEqual(row.value, 6)
        self.assertEqual(row.source, f"weather:{self.region.pk}")
        self.assertLess(row.change_per_day, 0)

    def test_reroll_replaces_shelter_rows(self):
        from world.locations.constants import KeyType
        from world.locations.models import LocationValueModifier

        clear = WeatherTypeFactory(name="ClearSky")
        roll_region_weather(self.region, weather_type=self.overcast)
        roll_region_weather(self.region, weather_type=clear)
        self.assertEqual(
            LocationValueModifier.objects.filter(
                area=self.region, key_type=KeyType.DAMAGE_TYPE
            ).count(),
            0,
        )

    def test_overcast_raises_felt_sun_shade(self):
        """The #2846 coupling: cloudy weather reduces felt sun exposure via shade."""
        from unittest.mock import patch

        from world.character_sheets.factories import CharacterSheetFactory
        from world.game_clock.constants import TimePhase
        from world.species.sun_exposure import felt_sun_exposure

        profile = RoomProfileFactory(is_outdoor=True, area=self.region)
        room = profile.objectdb
        sheet = CharacterSheetFactory()
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY):
            before = felt_sun_exposure(sheet.character, room)
            roll_region_weather(self.region, weather_type=self.overcast)
            after = felt_sun_exposure(sheet.character, room)
        self.assertEqual(before.shade, 0)
        self.assertEqual(after.shade, 6)
        self.assertEqual(after.residual, before.residual - 6)


class PhaseAlignedWeatherTickTests(TestCase):
    """#2845: the weather tick fires only at IC time-of-day phase boundaries."""

    def _guard(self):
        from world.weather.tasks import _phase_transitioned_since_last_run

        return _phase_transitioned_since_last_run()

    def _stamp(self, ic_dt):
        from world.game_clock.models import ScheduledTaskRecord
        from world.weather.tasks import WEATHER_TASK_KEY

        record, _ = ScheduledTaskRecord.objects.get_or_create(task_key=WEATHER_TASK_KEY)
        record.last_ic_run_at = ic_dt
        record.save(update_fields=["last_ic_run_at"])

    def test_no_clock_never_fires(self):
        from unittest.mock import patch

        with patch("world.game_clock.services.get_ic_now", return_value=None):
            assert self._guard() is False

    def test_first_run_fires(self):
        from datetime import UTC, datetime
        from unittest.mock import patch

        noon = datetime(2020, 5, 10, 12, 0, tzinfo=UTC)
        with patch("world.game_clock.services.get_ic_now", return_value=noon):
            assert self._guard() is True

    def test_same_phase_noops_boundary_fires(self):
        from datetime import UTC, datetime
        from unittest.mock import patch

        noon = datetime(2020, 5, 10, 12, 0, tzinfo=UTC)
        one_pm = datetime(2020, 5, 10, 13, 0, tzinfo=UTC)
        night = datetime(2020, 5, 10, 20, 30, tzinfo=UTC)
        self._stamp(noon)
        with patch("world.game_clock.services.get_ic_now", return_value=one_pm):
            assert self._guard() is False
        with patch("world.game_clock.services.get_ic_now", return_value=night):
            assert self._guard() is True


class WeatherTransitionGraphTests(TestCase):
    """#2845/ADR-0181: the roll walks the authored transition graph when edges exist.

    Pure picker tests — no Areas (matview-free); ``_pick_next_weather`` takes the
    current state row and the eligible candidates directly.
    """

    def _state(self, weather_type):
        from world.weather.models import RegionWeatherState

        return RegionWeatherState(weather_type=weather_type)

    def test_outgoing_edges_restrict_the_roll(self):
        from world.weather.factories import WeatherTransitionFactory
        from world.weather.services import _pick_next_weather

        clear = WeatherTypeFactory(name="TClear")
        overcast = WeatherTypeFactory(name="TOvercast")
        storm = WeatherTypeFactory(name="TStorm")
        WeatherTransitionFactory(from_type=clear, to_type=clear, weight=1)
        WeatherTransitionFactory(from_type=clear, to_type=overcast, weight=1)
        # No clear->storm edge: a storm can never follow a cloudless sky.
        for _ in range(25):
            picked = _pick_next_weather(self._state(clear), [clear, overcast, storm])
            assert picked in (clear, overcast)

    def test_no_edges_falls_back_to_global_weights(self):
        from world.weather.services import _pick_next_weather

        clear = WeatherTypeFactory(name="TClear2")
        storm = WeatherTypeFactory(name="TStorm2")
        picked = _pick_next_weather(self._state(clear), [storm])
        assert picked == storm

    def test_eligibility_pruned_graph_falls_back(self):
        """Edges exist but none of their destinations are climate-eligible -> global roll."""
        from world.weather.factories import WeatherTransitionFactory
        from world.weather.services import _pick_next_weather

        clear = WeatherTypeFactory(name="TClear3")
        snow = WeatherTypeFactory(name="TSnow3")
        fog = WeatherTypeFactory(name="TFog3")
        WeatherTransitionFactory(from_type=clear, to_type=snow, weight=5)
        picked = _pick_next_weather(self._state(clear), [fog])
        assert picked == fog

    def test_no_current_state_uses_global_weights(self):
        from world.weather.services import _pick_next_weather

        fog = WeatherTypeFactory(name="TFog4")
        assert _pick_next_weather(None, [fog]) == fog
