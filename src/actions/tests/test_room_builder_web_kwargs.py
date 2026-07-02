"""Web-addressable Room Builder kwargs (#670 PR2): room_id / to_room_id / exit_id.

The web canvas operates building-wide by id while telnet anchors to
``actor.location``. These tests pin the explicit-id path: the action mutates
the identified room, and ``IsRoomOwnerPrerequisite`` gates on the *resolved*
room rather than wherever the actor happens to stand.
"""

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import RoomProfile, RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership


def _room_in(area, *, size=None, grid=(None, None, 0), name="A Room"):
    room = ObjectDB.objects.create(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={
            "area": area,
            "size": size,
            "grid_x": grid[0],
            "grid_y": grid[1],
            "floor": grid[2],
        },
    )
    return room


def _owned_building(persona, *, budget=100):
    area = AreaFactory(level=AreaLevel.BUILDING)
    building = BuildingFactory(area=area, space_budget=budget)
    LocationOwnership.objects.create(
        parent_type=LocationParentType.AREA,
        area=area,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )
    return building


@tag("postgres")  # is_owner walks the areas_areaclosure materialized view (PG-only)
class WebKwargsBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_room_size_tiers()
        cls.snug = RoomSizeTier.objects.get(name="Snug")
        cls.modest = RoomSizeTier.objects.get(name="Modest")
        cls.actor = CharacterFactory()
        CharacterSheetFactory(character=cls.actor)
        cls.persona = cls.actor.sheet_data.primary_persona
        cls.building = _owned_building(cls.persona)
        cls.entry = _room_in(cls.building.area, size=cls.modest, grid=(0, 0, 0), name="Entry Hall")
        cls.building.entry_room = cls.entry.room_profile
        cls.building.save(update_fields=["entry_room"])
        cls.study = _room_in(cls.building.area, size=cls.modest, grid=(1, 0, 0), name="Study")

    def setUp(self) -> None:
        self.actor.db_location = self.entry
        self.actor.save(update_fields=["db_location"])


class ExplicitRoomIdTests(WebKwargsBase):
    def test_resize_targets_the_identified_room_not_location(self) -> None:
        result = get_action("resize_room").run(actor=self.actor, room_id=self.study.pk, size="Snug")
        self.assertTrue(result.success, result.message)
        self.study.room_profile.refresh_from_db()
        self.assertEqual(self.study.room_profile.size, self.snug)
        self.entry.room_profile.refresh_from_db()
        self.assertEqual(self.entry.room_profile.size, self.modest)

    def test_dig_digs_off_the_identified_room(self) -> None:
        result = get_action("dig_room").run(
            actor=self.actor, room_id=self.study.pk, direction="north", name="Attic Stair"
        )
        self.assertTrue(result.success, result.message)
        out = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit", db_location=self.study
        )
        self.assertEqual(out.db_key, "north")

    def test_missing_room_id_fails_cleanly(self) -> None:
        result = get_action("resize_room").run(actor=self.actor, room_id=999999, size="Snug")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "No such room.")

    def test_link_rooms_accepts_to_room_id(self) -> None:
        far = _room_in(self.building.area, size=self.modest, grid=(5, 5, 0), name="Far Wing")
        result = get_action("link_rooms").run(
            actor=self.actor,
            room_id=self.study.pk,
            to_room_id=far.pk,
            name_there="arched door",
            name_back="back to the study",
        )
        self.assertTrue(result.success, result.message)
        out = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit", db_location=self.study
        )
        self.assertEqual(out.db_key, "arched door")
        self.assertEqual(out.db_destination, far)


class ExplicitExitIdTests(WebKwargsBase):
    def _linked_exit(self) -> ObjectDB:
        get_action("link_rooms").run(
            actor=self.actor,
            room_id=self.study.pk,
            to_room_id=self.entry.pk,
            name_there="service door",
            name_back="service door back",
        )
        return ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.study,
            db_key="service door",
        )

    def test_rename_exit_by_id(self) -> None:
        exit_obj = self._linked_exit()
        result = get_action("rename_exit").run(
            actor=self.actor, room_id=self.study.pk, exit_id=exit_obj.pk, name="grand stair"
        )
        self.assertTrue(result.success, result.message)
        exit_obj.refresh_from_db()
        self.assertEqual(exit_obj.db_key, "grand stair")

    def test_unlink_by_id_removes_the_pair(self) -> None:
        exit_obj = self._linked_exit()
        # A second study↔entry link keeps the graph connected past the guard.
        get_action("link_rooms").run(
            actor=self.actor,
            room_id=self.study.pk,
            to_room_id=self.entry.pk,
            name_there="main hall door",
            name_back="back to the study proper",
        )
        result = get_action("unlink_rooms").run(
            actor=self.actor, room_id=self.study.pk, exit_id=exit_obj.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            ObjectDB.objects.filter(
                db_typeclass_path="typeclasses.exits.Exit",
                db_location__in=[self.study, self.entry],
                db_key__startswith="service door",
            ).exists()
        )

    def test_exit_id_must_live_in_the_anchor_room(self) -> None:
        exit_obj = self._linked_exit()
        result = get_action("rename_exit").run(
            actor=self.actor, room_id=self.entry.pk, exit_id=exit_obj.pk, name="nope"
        )
        self.assertFalse(result.success)


class OwnershipGateTests(WebKwargsBase):
    def test_stranger_cannot_reach_into_the_building(self) -> None:
        stranger = CharacterFactory()
        CharacterSheetFactory(character=stranger)
        stranger_home = _owned_building(stranger.sheet_data.primary_persona)
        stranger_room = _room_in(stranger_home.area, grid=(0, 0, 0), name="Hovel")
        stranger.db_location = stranger_room
        stranger.save(update_fields=["db_location"])

        result = get_action("resize_room").run(actor=stranger, room_id=self.study.pk, size="Snug")
        self.assertFalse(result.success)
        self.study.room_profile.refresh_from_db()
        self.assertEqual(self.study.room_profile.size, self.modest)

    def test_owner_standing_at_home_cannot_target_foreign_building(self) -> None:
        other = CharacterFactory()
        CharacterSheetFactory(character=other)
        other_building = _owned_building(other.sheet_data.primary_persona)
        other_room = _room_in(other_building.area, grid=(0, 0, 0), name="Foreign Hall")

        result = get_action("resize_room").run(actor=self.actor, room_id=other_room.pk, size="Snug")
        self.assertFalse(result.success)


class PlaceRoomActionTests(WebKwargsBase):
    def test_place_room_by_id(self) -> None:
        result = get_action("place_room").run(
            actor=self.actor, room_id=self.study.pk, grid_x=2, grid_y=2, floor=0
        )
        self.assertTrue(result.success, result.message)
        self.study.room_profile.refresh_from_db()
        self.assertEqual((self.study.room_profile.grid_x, self.study.room_profile.grid_y), (2, 2))

    def test_place_room_needs_coordinates(self) -> None:
        result = get_action("place_room").run(actor=self.actor, room_id=self.study.pk)
        self.assertFalse(result.success)

    def test_place_room_occupied_cell_surfaces_error(self) -> None:
        result = get_action("place_room").run(
            actor=self.actor, room_id=self.study.pk, grid_x=0, grid_y=0, floor=0
        )
        self.assertFalse(result.success)
