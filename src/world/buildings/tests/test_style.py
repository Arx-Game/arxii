"""Architectural style → climate-affinity materialization (#1514)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import ArchitecturalStyle, StyleAffinity
from world.buildings.services import set_building_style, sync_building_style_modifiers
from world.locations.constants import StatKey
from world.locations.services import effective_value


class BuildingStyleTests(TestCase):
    def _style(self, name: str, **affinities: int) -> ArchitecturalStyle:
        style = ArchitecturalStyle.objects.create(name=name)
        for stat_key, value in affinities.items():
            StyleAffinity.objects.create(style=style, stat_key=stat_key, value=value)
        return style

    def _building_with_room(self):
        building = BuildingFactory()
        room = RoomProfileFactory(area=building.area).objectdb
        return building, room

    def test_assigning_a_style_materializes_affinities_on_its_rooms(self) -> None:
        # Open-air: cold-vulnerable (+COLD) and well-ventilated (−HEAT).
        style = self._style("Open-Air Reefian", **{StatKey.COLD: 6, StatKey.HEAT: -3})
        building, room = self._building_with_room()

        set_building_style(building, style)

        assert effective_value(room, stat_key=StatKey.COLD) == 6  # vulnerability bites
        assert effective_value(room, stat_key=StatKey.HEAT) == 0  # −HEAT floors (no heat to cut)

    def test_changing_style_replaces_the_old_modifiers(self) -> None:
        building, room = self._building_with_room()
        set_building_style(building, self._style("Drafty", **{StatKey.COLD: 6}))
        assert effective_value(room, stat_key=StatKey.COLD) == 6

        set_building_style(building, self._style("Snug", **{StatKey.COLD: 2}))
        assert effective_value(room, stat_key=StatKey.COLD) == 2  # old +6 row gone, not stacked

    def test_clearing_style_removes_its_modifiers(self) -> None:
        building, room = self._building_with_room()
        set_building_style(building, self._style("Drafty", **{StatKey.COLD: 6}))
        assert effective_value(room, stat_key=StatKey.COLD) == 6

        set_building_style(building, None)
        assert effective_value(room, stat_key=StatKey.COLD) == 0

    def test_sync_is_idempotent(self) -> None:
        building, room = self._building_with_room()
        set_building_style(building, self._style("Drafty", **{StatKey.COLD: 6}))
        sync_building_style_modifiers(building)
        sync_building_style_modifiers(building)
        assert effective_value(room, stat_key=StatKey.COLD) == 6  # not doubled to 12
