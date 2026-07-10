"""Climate → comfort: exposure axes, enclosure, and the points→level→multiplier engine (#1514).

These tests pin the design invariants: each exposure axis is floored at 0, so a
counter-fixture (a negative modifier) can zero out *its* axis but never drive it
negative or touch another axis ("a hearth eats cold and can never overheat a room"); enclosure
gates weather; and comfort points map to a 1–10 level driving an AP-regen multiplier.
"""

from django.test import TestCase

from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import (
    ap_regen_multiplier_pct,
    comfort_level,
    comfort_level_for_points,
    comfort_points,
    comfort_summary,
    effective_value,
    felt_exposure,
    room_discomfort,
    room_enclosure,
)


class ComfortAxesTests(TestCase):
    def _room_in_ward(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        return ward, profile.objectdb

    def _modifier(self, area, stat_key: StatKey, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=area, stat_key=stat_key, value=value
        )

    def test_neutral_room_is_perfectly_comfortable(self) -> None:
        _, room = self._room_in_ward()
        assert effective_value(room, stat_key=StatKey.COLD) == 0
        assert effective_value(room, stat_key=StatKey.HEAT) == 0
        assert room_discomfort(room) == 0
        assert comfort_points(room) == 0

    def test_counter_in_an_unaffected_room_does_nothing_and_never_harms(self) -> None:
        # A hearth (COLD mitigation) in a room with no cold source: COLD floors at 0,
        # HEAT is untouched. The fireplace can't make the room "negative cold" or hot.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.COLD) == 0  # floored, not negative
        assert effective_value(room, stat_key=StatKey.HEAT) == 0  # untouched
        assert comfort_points(room) == 0

    def test_partial_mitigation_leaves_residual_discomfort(self) -> None:
        # Climate +6 cold, hearth -4 → residual 2 cold.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 6)
        self._modifier(ward, StatKey.COLD, -4)
        assert effective_value(room, stat_key=StatKey.COLD) == 2
        assert comfort_points(room) == -2

    def test_over_mitigation_floors_at_zero_no_overcorrection(self) -> None:
        # Climate +4 cold, hearth -10 → 0 (not -6); the counter can't flip the sign.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 4)
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.COLD) == 0
        assert comfort_points(room) == 0

    def test_cold_counter_never_touches_heat(self) -> None:
        # A heatwave (+5 HEAT) plus a hearth (-10 COLD): the hearth is useless against
        # heat but harmless — HEAT stays 5, COLD floors at 0.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.HEAT, 5)
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.HEAT) == 5
        assert effective_value(room, stat_key=StatKey.COLD) == 0
        assert comfort_points(room) == -5

    def test_discomfort_sums_across_axes(self) -> None:
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 3)
        self._modifier(ward, StatKey.HEAT, 5)
        assert room_discomfort(room) == 8
        assert comfort_points(room) == -8


class EnclosureShelteringTests(TestCase):
    """Enclosure gates the *weather* axes (WET, WIND) but never temperature (#1514)."""

    def _room(self, enclosure: RoomEnclosure):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward, enclosure=enclosure)
        return ward, profile.objectdb

    def _weather(self, area, stat_key: StatKey, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=area, stat_key=stat_key, value=value
        )

    def test_open_air_feels_all_weather(self) -> None:
        ward, room = self._room(RoomEnclosure.OPEN_AIR)
        self._weather(ward, StatKey.WET, 8)
        self._weather(ward, StatKey.WIND, 5)
        assert felt_exposure(room, stat_key=StatKey.WET) == 8
        assert felt_exposure(room, stat_key=StatKey.WIND) == 5
        assert comfort_points(room) == -13

    def test_roof_blocks_rain_not_wind(self) -> None:
        ward, room = self._room(RoomEnclosure.ROOFED)
        self._weather(ward, StatKey.WET, 8)
        self._weather(ward, StatKey.WIND, 5)
        assert felt_exposure(room, stat_key=StatKey.WET) == 0  # roof sheds rain/snow
        assert felt_exposure(room, stat_key=StatKey.WIND) == 5  # wind still reaches you
        assert comfort_points(room) == -5

    def test_walls_block_rain_and_wind(self) -> None:
        ward, room = self._room(RoomEnclosure.WALLED)
        self._weather(ward, StatKey.WET, 8)
        self._weather(ward, StatKey.WIND, 5)
        assert felt_exposure(room, stat_key=StatKey.WET) == 0
        assert felt_exposure(room, stat_key=StatKey.WIND) == 0
        assert comfort_points(room) == 0

    def test_enclosure_never_shelters_temperature(self) -> None:
        # Even a sealed room feels the cold — insulation is fixtures/style, not enclosure.
        ward, room = self._room(RoomEnclosure.SEALED)
        self._weather(ward, StatKey.COLD, 7)
        assert felt_exposure(room, stat_key=StatKey.COLD) == 7
        assert comfort_points(room) == -7

    def test_default_enclosure_is_walled(self) -> None:
        room = RoomProfileFactory().objectdb  # no enclosure passed → column default
        assert room_enclosure(room) == RoomEnclosure.WALLED


class ComfortLevelTests(TestCase):
    """The wide points pool → 1–10 level → AP-regen multiplier (#1514)."""

    def _room(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        return ward, RoomProfileFactory(area=ward).objectdb

    def _modifier(self, area, stat_key: StatKey, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=area, stat_key=stat_key, value=value
        )

    def test_amenity_raises_points_discomfort_lowers_them(self) -> None:
        ward, room = self._room()
        self._modifier(ward, StatKey.AMENITY, 2500)
        self._modifier(ward, StatKey.COLD, 500)
        assert comfort_points(room) == 2000  # 2500 amenity − 500 felt cold

    def test_point_bands_map_to_levels(self) -> None:
        # 5 = neutral ("Fine", 0–100); exponential cuts to the ±10k ends.
        assert comfort_level_for_points(0) == 5
        assert comfort_level_for_points(50) == 5
        assert comfort_level_for_points(100) == 6
        assert comfort_level_for_points(2500) == 8  # difficult-but-realistic
        assert comfort_level_for_points(10_000) == 10
        assert comfort_level_for_points(-1) == 4
        assert comfort_level_for_points(-3000) == 3
        assert comfort_level_for_points(-10_000) == 2
        assert comfort_level_for_points(-50_000) == 1  # below the lowest floor

    def test_comfort_level_reads_the_room_pool(self) -> None:
        ward, room = self._room()
        self._modifier(ward, StatKey.AMENITY, 2500)
        assert comfort_level(room) == 8

    def test_comfort_offset_applies_per_character_conditions(self) -> None:
        # A wound (−2500 comfort) cancels a luxurious room back to neutral.
        ward, room = self._room()
        self._modifier(ward, StatKey.AMENITY, 2500)
        assert comfort_level(room, comfort_offset=-2500) == 5

    def test_ap_regen_multiplier_table(self) -> None:
        assert ap_regen_multiplier_pct(5) == 0
        assert ap_regen_multiplier_pct(1) == -50
        assert ap_regen_multiplier_pct(8) == 25
        assert ap_regen_multiplier_pct(10) == 100

    def test_comfort_summary_reports_level_points_and_only_biting_axes(self) -> None:
        ward, room = self._room()
        self._modifier(ward, StatKey.COLD, 500)
        self._modifier(ward, StatKey.AMENITY, 50)
        summary = comfort_summary(room)
        assert summary.points == -450  # 50 amenity − 500 felt cold
        assert summary.level == comfort_level_for_points(-450)
        assert summary.amenity == 50
        assert summary.felt_exposures == {StatKey.COLD: 500}  # HEAT/WET/WIND omitted (0)


class WindowEnclosureTests(TestCase):
    def _modifier(self, area, stat_key: StatKey, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=area, stat_key=stat_key, value=value
        )

    def _room_with_profile(self):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward, enclosure=RoomEnclosure.WALLED)
        return ward, profile.objectdb

    def _window_in_room(self, room, is_open=False):
        exit_obj = ObjectDBFactory(
            db_key="window", db_typeclass_path="typeclasses.exits.Exit", location=room
        )
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.is_open = is_open
        profile.save()
        return exit_obj

    def test_open_window_lowers_enclosure_for_weather_axes(self):
        ward, room = self._room_with_profile()
        self._modifier(ward, StatKey.WIND, 5)
        self._window_in_room(room, is_open=True)
        # WALLED normally shelters WET/WIND; open window makes it ROOFED (shelters only WET).
        assert felt_exposure(room, stat_key=StatKey.WET) == 0
        assert felt_exposure(room, stat_key=StatKey.WIND) == 5

    def test_closed_window_keeps_weather_sheltered(self):
        ward, room = self._room_with_profile()
        self._modifier(ward, StatKey.WIND, 5)
        self._window_in_room(room, is_open=False)
        assert felt_exposure(room, stat_key=StatKey.WET) == 0
        assert felt_exposure(room, stat_key=StatKey.WIND) == 0

    def test_open_window_does_not_affect_temperature_axes(self):
        ward, room = self._room_with_profile()
        self._modifier(ward, StatKey.COLD, 5)
        self._window_in_room(room, is_open=True)
        assert felt_exposure(room, stat_key=StatKey.COLD) == 5
