"""Climate → comfort exposure axes + comfort_score (#1514, slice 1).

These tests pin the design invariants: each exposure axis is floored at 0, so a
counter-fixture (a negative modifier) can zero out *its* axis but never drive it
negative or touch another axis. "A hearth eats cold and can never overheat a room."
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import comfort_score, effective_value, room_discomfort


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
        assert comfort_score(room) == 0

    def test_counter_in_an_unaffected_room_does_nothing_and_never_harms(self) -> None:
        # A hearth (COLD mitigation) in a room with no cold source: COLD floors at 0,
        # HEAT is untouched. The fireplace can't make the room "negative cold" or hot.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.COLD) == 0  # floored, not negative
        assert effective_value(room, stat_key=StatKey.HEAT) == 0  # untouched
        assert comfort_score(room) == 0

    def test_partial_mitigation_leaves_residual_discomfort(self) -> None:
        # Climate +6 cold, hearth -4 → residual 2 cold.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 6)
        self._modifier(ward, StatKey.COLD, -4)
        assert effective_value(room, stat_key=StatKey.COLD) == 2
        assert comfort_score(room) == -2

    def test_over_mitigation_floors_at_zero_no_overcorrection(self) -> None:
        # Climate +4 cold, hearth -10 → 0 (not -6); the counter can't flip the sign.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 4)
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.COLD) == 0
        assert comfort_score(room) == 0

    def test_cold_counter_never_touches_heat(self) -> None:
        # A heatwave (+5 HEAT) plus a hearth (-10 COLD): the hearth is useless against
        # heat but harmless — HEAT stays 5, COLD floors at 0.
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.HEAT, 5)
        self._modifier(ward, StatKey.COLD, -10)
        assert effective_value(room, stat_key=StatKey.HEAT) == 5
        assert effective_value(room, stat_key=StatKey.COLD) == 0
        assert comfort_score(room) == -5

    def test_discomfort_sums_across_axes(self) -> None:
        ward, room = self._room_in_ward()
        self._modifier(ward, StatKey.COLD, 3)
        self._modifier(ward, StatKey.HEAT, 5)
        assert room_discomfort(room) == 8
        assert comfort_score(room) == -8
