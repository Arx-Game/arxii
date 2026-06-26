"""Comfort decorations — mitigation (cancel) + amenity (add), and stacking (#1514)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.models import DecorationAffinity, DecorationKind, RoomDecoration
from world.buildings.services import place_decoration, remove_decoration
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.locations.services import comfort_points, effective_value


class DecorationTests(TestCase):
    def _room_with_cold(self, cold: int = 0):
        ward = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=ward)
        if cold:
            LocationValueModifier.objects.create(
                parent_type=LocationParentType.AREA, area=ward, stat_key=StatKey.COLD, value=cold
            )
        return profile

    def _hearth(self) -> DecorationKind:
        # Mostly a COLD counter (big), a little cosy (small amenity).
        kind = DecorationKind.objects.create(name="Hearth", amenity=50)
        DecorationAffinity.objects.create(kind=kind, stat_key=StatKey.COLD, value=-2000)
        return kind

    def test_decoration_cancels_discomfort_and_adds_a_little_amenity(self) -> None:
        profile = self._room_with_cold(1500)
        room = profile.objectdb
        assert comfort_points(room) == -1500  # freezing

        place_decoration(profile, self._hearth())
        assert effective_value(room, stat_key=StatKey.COLD) == 0  # 1500 − 2000, floored
        assert effective_value(room, stat_key=StatKey.AMENITY) == 50
        assert comfort_points(room) == 50  # cancelled the cold + the small cosy bonus

    def test_counter_in_a_warm_room_only_adds_its_small_amenity_never_harms(self) -> None:
        profile = self._room_with_cold(0)  # no cold to cancel
        room = profile.objectdb
        place_decoration(profile, self._hearth())
        assert effective_value(room, stat_key=StatKey.COLD) == 0  # −2000 floors, no negative cold
        assert comfort_points(room) == 50  # just the cosy amenity

    def test_luxury_decoration_is_mostly_amenity(self) -> None:
        profile = self._room_with_cold(0)
        room = profile.objectdb
        place_decoration(profile, DecorationKind.objects.create(name="Marble Bath", amenity=3000))
        assert comfort_points(room) == 3000

    def test_decorations_stack(self) -> None:
        profile = self._room_with_cold(0)
        room = profile.objectdb
        place_decoration(profile, DecorationKind.objects.create(name="Rug", amenity=200))
        place_decoration(profile, DecorationKind.objects.create(name="Tapestry", amenity=300))
        assert comfort_points(room) == 500

    def test_removing_a_decoration_deletes_its_modifiers(self) -> None:
        profile = self._room_with_cold(1500)
        room = profile.objectdb
        decoration = place_decoration(profile, self._hearth())
        assert comfort_points(room) == 50

        remove_decoration(decoration)
        assert comfort_points(room) == -1500  # back to freezing
        assert RoomDecoration.objects.count() == 0
