"""Room Builder services (#670): dig / resize / remove / link / budgets."""

from django.test import TestCase

from evennia_extensions.models import ObjectDisplayData, RoomProfile, RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.room_services import (
    RoomBuildError,
    dig_room,
    space_remaining,
    space_used,
)
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.scenes.factories import PersonaFactory


def _room_in(area, *, size=None, grid=(None, None, 0), name="A Room"):
    from evennia.objects.models import ObjectDB

    room = ObjectDB.objects.create(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    profile, _ = RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={
            "area": area,
            "size": size,
            "grid_x": grid[0],
            "grid_y": grid[1],
            "floor": grid[2],
        },
    )
    return profile


class RoomBuilderBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_room_size_tiers()
        cls.modest = RoomSizeTier.objects.get(name="Modest")
        cls.snug = RoomSizeTier.objects.get(name="Snug")
        area = AreaFactory(level=AreaLevel.BUILDING)
        cls.building = BuildingFactory(area=area, space_budget=100)
        cls.entry = _room_in(area, size=cls.modest, grid=(0, 0, 0), name="Entry Hall")
        cls.building.entry_room = cls.entry
        cls.building.save(update_fields=["entry_room"])
        cls.owner = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=cls.owner,
        )
        cls.stranger = PersonaFactory()


class SpaceBudgetTests(RoomBuilderBase):
    def test_space_used_sums_room_units(self) -> None:
        self.assertEqual(space_used(self.building), 25)
        _room_in(self.building.area, size=self.snug)
        self.assertEqual(space_used(self.building), 35)
        self.assertEqual(space_remaining(self.building), 65)

    def test_unsized_rooms_count_zero(self) -> None:
        _room_in(self.building.area, size=None)
        self.assertEqual(space_used(self.building), 25)


class DigRoomTests(RoomBuilderBase):
    def test_dig_creates_room_exit_pair_and_coords(self) -> None:
        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="north",
            name="Kitchen",
        )
        from evennia.objects.models import ObjectDB

        self.assertEqual(profile.area, self.building.area)
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (0, 1, 0))
        exits = ObjectDB.objects.filter(db_typeclass_path="typeclasses.exits.Exit")
        out = exits.get(db_location=self.entry.objectdb)
        self.assertEqual(out.db_key, "north")
        self.assertEqual(out.db_destination, profile.objectdb)
        back = exits.get(db_location=profile.objectdb)
        self.assertEqual(back.db_key, "south")
        self.assertEqual(back.db_destination, self.entry.objectdb)

    def test_dig_defaults(self) -> None:
        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="east",
            name="Pantry",
        )
        self.assertEqual(profile.size, self.modest)
        display = ObjectDisplayData.objects.get(object=profile.objectdb)
        self.assertEqual(display.permanent_description, "An unfinished room.")

    def test_dig_like_copies_size_and_desc(self) -> None:
        exemplar = _room_in(self.building.area, size=self.snug, name="West Corridor")
        ObjectDisplayData.objects.create(
            object=exemplar.objectdb, permanent_description="A featureless corridor."
        )
        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="west",
            name="Hall",
            like=exemplar.objectdb,
        )
        self.assertEqual(profile.size, self.snug)
        display = ObjectDisplayData.objects.get(object=profile.objectdb)
        self.assertEqual(display.permanent_description, "A featureless corridor.")

    def test_dig_over_budget_refused(self) -> None:
        vast = RoomSizeTier.objects.get(name="Vast")  # 250 > 100 budget
        with self.assertRaises(RoomBuildError) as caught:
            dig_room(
                persona=self.owner,
                from_room=self.entry.objectdb,
                direction="north",
                name="Ballroom",
                size=vast,
            )
        self.assertIn("75 of 100", caught.exception.user_message)

    def test_dig_coord_collision_lands_unplaced(self) -> None:
        _room_in(self.building.area, size=self.snug, grid=(0, 1, 0), name="Blocker")
        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="north",
            name="Kitchen",
        )
        self.assertIsNone(profile.grid_x)
        self.assertIsNone(profile.grid_y)

    def test_dig_up_changes_floor(self) -> None:
        profile = dig_room(
            persona=self.owner,
            from_room=self.entry.objectdb,
            direction="up",
            name="Solar",
        )
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (0, 0, 1))

    def test_dig_unknown_direction_refused(self) -> None:
        with self.assertRaises(RoomBuildError):
            dig_room(
                persona=self.owner,
                from_room=self.entry.objectdb,
                direction="oak door",
                name="Study",
            )

    def test_dig_requires_owner(self) -> None:
        with self.assertRaises(RoomBuildError):
            dig_room(
                persona=self.stranger,
                from_room=self.entry.objectdb,
                direction="north",
                name="Kitchen",
            )


class PlaceRoomTests(RoomBuilderBase):
    def test_place_sets_coords(self) -> None:
        from world.buildings.room_services import place_room

        loose = _room_in(self.building.area, size=self.snug, name="Loose Room")
        profile = place_room(persona=self.owner, room=loose.objectdb, grid_x=2, grid_y=3, floor=1)
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (2, 3, 1))

    def test_place_defaults_to_current_floor(self) -> None:
        from world.buildings.room_services import place_room

        attic = _room_in(self.building.area, size=self.snug, grid=(4, 4, 2), name="Attic")
        profile = place_room(persona=self.owner, room=attic.objectdb, grid_x=5, grid_y=4)
        self.assertEqual((profile.grid_x, profile.grid_y, profile.floor), (5, 4, 2))

    def test_place_onto_occupied_cell_refused(self) -> None:
        from world.buildings.room_services import place_room

        loose = _room_in(self.building.area, size=self.snug, name="Loose Room")
        with self.assertRaises(RoomBuildError):
            place_room(persona=self.owner, room=loose.objectdb, grid_x=0, grid_y=0, floor=0)

    def test_place_onto_own_cell_is_noop_success(self) -> None:
        from world.buildings.room_services import place_room

        profile = place_room(
            persona=self.owner, room=self.entry.objectdb, grid_x=0, grid_y=0, floor=0
        )
        self.assertEqual((profile.grid_x, profile.grid_y), (0, 0))

    def test_place_requires_owner(self) -> None:
        from world.buildings.room_services import place_room

        with self.assertRaises(RoomBuildError):
            place_room(persona=self.stranger, room=self.entry.objectdb, grid_x=1, grid_y=1)
