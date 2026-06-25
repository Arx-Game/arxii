"""`where` service (#1463) — coloured area-path rendering with colour inheritance."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.services import colored_area_path


class ColoredAreaPathTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = AreaFactory(name="Umbros", level=AreaLevel.REGION, color="|y")
        # Ward leaves colour blank → inherits the region's |y.
        cls.ward = AreaFactory(name="Blackgate Ward", level=AreaLevel.WARD, parent=cls.region)
        # Building overrides to |r.
        cls.building = AreaFactory(
            name="Sable Hold", level=AreaLevel.BUILDING, parent=cls.ward, color="|r"
        )
        cls.profile = RoomProfileFactory(area=cls.building)
        cls.room = cls.profile.objectdb

    def test_colours_inherit_down_and_can_be_overridden(self) -> None:
        path = colored_area_path(self.room)
        assert "|yUmbros|n" in path
        assert "|yBlackgate Ward|n" in path  # inherited
        assert "|rSable Hold|n" in path  # override

    def test_segments_are_outermost_first(self) -> None:
        path = colored_area_path(self.room)
        assert path.index("Umbros") < path.index("Blackgate Ward") < path.index("Sable Hold")

    def test_room_without_area_returns_plain_name(self) -> None:
        profile = RoomProfileFactory(area=None)
        path = colored_area_path(profile.objectdb)
        assert "|" not in path
        assert path == profile.objectdb.key
