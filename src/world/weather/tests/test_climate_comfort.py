"""Climate → comfort integration (#1522): regional baseline folds into the felt exposure.

The payoff slice: a region's climate is *mechanical*. A desert room is genuinely hotter,
a cooling fixture fights that heat by combining with it *before* the 0-floor (build-to-win),
enclosure never shelters climate temperature, and a winter month can push a temperate region
into real cold — all through the same comfort cascade the rest of #1514 already reads.
"""

from datetime import UTC, datetime

from django.test import TestCase

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.game_clock.factories import GameClockFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import comfort_points, felt_exposure, room_discomfort
from world.weather.constants import MONTH_TEMPERATURE_SHIFT
from world.weather.factories import ClimateFactory


class ClimateComfortIntegrationTests(TestCase):
    def _room(self, climate, *, enclosure=RoomEnclosure.WALLED):
        region = AreaFactory(level=AreaLevel.CITY, climate=climate)
        ward = AreaFactory(level=AreaLevel.WARD, parent=region)
        profile = RoomProfileFactory(area=ward, enclosure=enclosure)
        return ward, profile.objectdb

    def _modifier(self, area, stat_key: StatKey, value: int) -> None:
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA, area=area, stat_key=stat_key, value=value
        )

    def test_desert_room_is_mechanically_hot(self) -> None:
        desert = ClimateFactory(temperature=50, moisture=-50)
        _, room = self._room(desert)
        assert felt_exposure(room, stat_key=StatKey.HEAT) == 50
        assert felt_exposure(room, stat_key=StatKey.DRY) == 50
        assert felt_exposure(room, stat_key=StatKey.COLD) == 0
        # HEAT + DRY both bite; nothing else.
        assert room_discomfort(room) == 100
        assert comfort_points(room) == -100

    def test_cooling_fixture_fights_climate_before_the_floor(self) -> None:
        # Build-to-win: a desert HEAT +50 baseline with an AC fixture (-30) → felt 20,
        # NOT floored to 0 (the fixture combines with climate in one pre-floor sum).
        desert = ClimateFactory(temperature=50, moisture=0)
        ward, room = self._room(desert)
        self._modifier(ward, StatKey.HEAT, -30)
        assert felt_exposure(room, stat_key=StatKey.HEAT) == 20

    def test_over_cooling_floors_at_zero(self) -> None:
        desert = ClimateFactory(temperature=50, moisture=0)
        ward, room = self._room(desert)
        self._modifier(ward, StatKey.HEAT, -70)
        assert felt_exposure(room, stat_key=StatKey.HEAT) == 0  # floored, never negative

    def test_enclosure_never_shelters_climate_temperature(self) -> None:
        # Even sealed, a desert room feels the heat — insulation is fixtures, not walls.
        desert = ClimateFactory(temperature=50, moisture=0)
        _, room = self._room(desert, enclosure=RoomEnclosure.SEALED)
        assert felt_exposure(room, stat_key=StatKey.HEAT) == 50

    def test_winter_pushes_temperate_region_into_cold(self) -> None:
        # Temperate baseline (0) + a paused January clock (coldest shift) → real COLD;
        # a tropical region under the same winter stays warm (no real winter).
        january = datetime(1010, 1, 15, 12, 0, tzinfo=UTC)
        GameClockFactory(anchor_ic_time=january, paused=True)
        winter_shift = MONTH_TEMPERATURE_SHIFT[1]  # negative

        temperate = ClimateFactory(temperature=0, moisture=0)
        _, temperate_room = self._room(temperate)
        assert felt_exposure(temperate_room, stat_key=StatKey.COLD) == -winter_shift
        assert felt_exposure(temperate_room, stat_key=StatKey.HEAT) == 0

        tropical = ClimateFactory(temperature=60, moisture=40)
        _, tropical_room = self._room(tropical)
        # 60 + (~-50 winter) → still net warm, no cold at all ("no real winter").
        assert felt_exposure(tropical_room, stat_key=StatKey.COLD) == 0
