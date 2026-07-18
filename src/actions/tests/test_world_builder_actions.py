"""Tests for the staff world-builder canvas actions (#2449).

Each action gets one ``.run()`` success test (staff, plain-int kwargs — the
REST dispatch shape, #2163) and one non-staff rejection test (no mutation).
Plus the invariant cases the task brief calls out by name: digging into a
non-AUTHORED area fails, removing an already-exported room fails, and a
cross-area link succeeds.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.constants import RoomEnclosure
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.factories import AreaFactory
from world.areas.grid_services import create_exit_pair
from world.areas.models import Area
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.factories import ClueFactory, ClueTriggerFactory, RoomClueFactory
from world.clues.models import ClueTrigger, RoomClue
from world.magic.factories import PortalAnchorFactory, PortalAnchorKindFactory
from world.magic.models import PortalAnchor
from world.room_features.factories import RoomFeatureInstanceFactory


def _staff_actor(db_key: str) -> ObjectDB:
    """A Character whose account is staff, with a working CharacterSheet+persona."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    CharacterSheetFactory(character=char)
    return char


def _player_actor(db_key: str) -> ObjectDB:
    """A Character whose account is NOT staff."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=False)
    char.db_account = account
    char.save()
    return char


def _staff_actor_without_sheet(db_key: str) -> ObjectDB:
    """A Character whose account is staff, with NO CharacterSheet."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    return char


def _exit_between(room_a: ObjectDB, room_b: ObjectDB, name_ab: str, name_ba: str):
    return create_exit_pair(
        name=name_ab,
        aliases=(),
        reverse_name=name_ba,
        reverse_aliases=(),
        room_a=room_a,
        room_b=room_b,
    )


class CreateAreaActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("CreateAreaStaff")
        self.player = _player_actor("CreateAreaPlayer")

    def test_staff_creates_area(self) -> None:
        from actions.definitions.world_builder import CreateAreaAction

        result = CreateAreaAction().run(
            self.staff, name="Golden Ward", slug="golden-ward", level=int(AreaLevel.WARD)
        )
        assert result.success
        area = Area.objects.get(slug="golden-ward")
        assert area.name == "Golden Ward"
        assert area.origin == GridOrigin.AUTHORED

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import CreateAreaAction

        result = CreateAreaAction().run(
            self.player, name="Golden Ward", slug="golden-ward", level=int(AreaLevel.WARD)
        )
        assert not result.success
        assert not Area.objects.filter(slug="golden-ward").exists()

    def test_invalid_level_surfaces_full_clean_error(self) -> None:
        from actions.definitions.world_builder import CreateAreaAction

        result = CreateAreaAction().run(self.staff, name="Bad Level", slug="bad-level", level=999)
        assert not result.success
        assert not Area.objects.filter(slug="bad-level").exists()


class EditAreaActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("EditAreaStaff")
        self.player = _player_actor("EditAreaPlayer")
        self.area = AreaFactory(name="Old Name", level=AreaLevel.WARD)

    def test_staff_edits_area(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        result = EditAreaAction().run(self.staff, area_id=self.area.pk, name="New Name")
        assert result.success
        self.area.refresh_from_db()
        assert self.area.name == "New Name"

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        result = EditAreaAction().run(self.player, area_id=self.area.pk, name="Hijacked")
        assert not result.success
        self.area.refresh_from_db()
        assert self.area.name == "Old Name"

    def test_slug_change_on_exported_area_is_refused(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        self.area.origin = GridOrigin.AUTHORED
        self.area.slug = "old-name"
        self.area.save()
        result = EditAreaAction().run(self.staff, area_id=self.area.pk, slug="new-name")
        assert not result.success
        self.area.refresh_from_db()
        assert self.area.slug == "old-name"

    def test_parent_level_violation_surfaces_as_failure_message(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        sibling = AreaFactory(name="Sibling Ward", level=AreaLevel.WARD)
        result = EditAreaAction().run(self.staff, area_id=self.area.pk, parent_id=sibling.pk)
        assert not result.success
        assert result.message
        # ``.refresh_from_db()`` doesn't reliably clear a SharedMemoryModel
        # instance's in-memory FK mutation (idmapper identity-map quirk) — query
        # the column value directly to prove nothing was actually persisted.
        raw_parent_id = (
            Area.objects.filter(pk=self.area.pk).values_list("parent_id", flat=True).first()
        )
        assert raw_parent_id is None


class StaffDigRoomActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("DigRoomStaff")
        self.player = _player_actor("DigRoomPlayer")
        self.authored_area = AreaFactory(
            name="Arx City", level=AreaLevel.CITY, origin=GridOrigin.AUTHORED, slug="arx-city"
        )
        self.story_area = AreaFactory(
            name="Story Ward", level=AreaLevel.WARD, origin=GridOrigin.STORY
        )

    def test_staff_digs_room(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff, area_id=self.authored_area.pk, name="Golden Hart Taproom"
        )
        assert result.success
        profile = RoomProfile.objects.get(fixture_key="arx-city/golden-hart-taproom")
        assert profile.origin == GridOrigin.AUTHORED
        assert profile.area_id == self.authored_area.pk

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.player, area_id=self.authored_area.pk, name="Golden Hart Taproom"
        )
        assert not result.success
        assert not RoomProfile.objects.filter(area=self.authored_area).exists()

    def test_dig_into_non_authored_area_fails(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff, area_id=self.story_area.pk, name="Should Not Exist"
        )
        assert not result.success
        assert not RoomProfile.objects.filter(area=self.story_area).exists()

    def test_malformed_grid_x_fails_gracefully(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.authored_area.pk,
            name="Should Not Exist",
            grid_x="abc",
        )
        assert not result.success
        assert not RoomProfile.objects.filter(area=self.authored_area).exists()

    def test_dig_onto_free_cell_keeps_explicit_coords(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.authored_area.pk,
            name="Empty Lot",
            grid_x=3,
            grid_y=4,
            floor=0,
        )
        assert result.success
        profile = RoomProfile.objects.get(fixture_key="arx-city/empty-lot")
        assert profile.grid_x == 3
        assert profile.grid_y == 4
        assert "unplaced" not in result.message

    def test_dig_onto_occupied_cell_creates_unplaced_room(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        RoomProfileFactory(
            area=self.authored_area, grid_x=3, grid_y=4, floor=0, origin=GridOrigin.AUTHORED
        )

        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.authored_area.pk,
            name="Crowded Lot",
            grid_x=3,
            grid_y=4,
            floor=0,
        )
        assert result.success
        profile = RoomProfile.objects.get(fixture_key="arx-city/crowded-lot")
        assert profile.grid_x is None
        assert profile.grid_y is None
        assert "unplaced" in result.message


class StaffEditRoomActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("EditRoomStaff")
        self.player = _player_actor("EditRoomPlayer")
        area = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=area)

    def test_staff_edits_room(self) -> None:
        from actions.definitions.world_builder import StaffEditRoomAction

        result = StaffEditRoomAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            name="The Great Hall",
            description="Lofty and lamplit.",
            is_social_hub=True,
            enclosure=RoomEnclosure.OPEN_AIR,
        )
        assert result.success
        display = ObjectDisplayData.objects.get(object=self.profile.objectdb)
        assert display.longname == "The Great Hall"
        assert display.permanent_description == "Lofty and lamplit."
        self.profile.refresh_from_db()
        assert self.profile.is_social_hub is True
        assert self.profile.enclosure == RoomEnclosure.OPEN_AIR

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffEditRoomAction

        result = StaffEditRoomAction().run(
            self.player, room_id=self.profile.objectdb_id, name="Hijacked"
        )
        assert not result.success
        assert not ObjectDisplayData.objects.filter(object=self.profile.objectdb).exists()

    def test_staff_without_sheet_can_edit_room(self) -> None:
        from actions.definitions.world_builder import StaffEditRoomAction

        staff_no_sheet = _staff_actor_without_sheet("EditRoomStaffNoSheet")
        result = StaffEditRoomAction().run(
            staff_no_sheet,
            room_id=self.profile.objectdb_id,
            name="Bare Staff Hall",
            description="No sheet needed.",
        )
        assert result.success
        display = ObjectDisplayData.objects.get(object=self.profile.objectdb)
        assert display.longname == "Bare Staff Hall"
        assert display.permanent_description == "No sheet needed."


class StaffLinkRoomsActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("LinkRoomsStaff")
        self.player = _player_actor("LinkRoomsPlayer")
        self.area_a = AreaFactory(name="Ward A", level=AreaLevel.WARD)
        self.area_b = AreaFactory(name="Ward B", level=AreaLevel.WARD)
        self.room_a = RoomProfileFactory(area=self.area_a)
        self.room_b = RoomProfileFactory(area=self.area_b)

    def test_staff_links_cross_area_rooms(self) -> None:
        from actions.definitions.world_builder import StaffLinkRoomsAction

        result = StaffLinkRoomsAction().run(
            self.staff,
            room_a_id=self.room_a.objectdb_id,
            room_b_id=self.room_b.objectdb_id,
            name_ab="North Door",
            name_ba="South Door",
        )
        assert result.success
        assert ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.room_a.objectdb,
            db_destination=self.room_b.objectdb,
        ).exists()
        assert ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.room_b.objectdb,
            db_destination=self.room_a.objectdb,
        ).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffLinkRoomsAction

        result = StaffLinkRoomsAction().run(
            self.player,
            room_a_id=self.room_a.objectdb_id,
            room_b_id=self.room_b.objectdb_id,
            name_ab="North Door",
            name_ba="South Door",
        )
        assert not result.success
        assert not ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit", db_location=self.room_a.objectdb
        ).exists()


class StaffUnlinkRoomsActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("UnlinkRoomsStaff")
        self.player = _player_actor("UnlinkRoomsPlayer")
        area = AreaFactory(level=AreaLevel.WARD)
        self.room_a = RoomProfileFactory(area=area)
        self.room_b = RoomProfileFactory(area=area)
        self.forward, self.backward = _exit_between(
            self.room_a.objectdb, self.room_b.objectdb, "North", "South"
        )

    def test_staff_unlinks_rooms(self) -> None:
        from actions.definitions.world_builder import StaffUnlinkRoomsAction

        result = StaffUnlinkRoomsAction().run(self.staff, exit_id=self.forward.pk)
        assert result.success
        assert not ObjectDB.objects.filter(pk=self.forward.pk).exists()
        assert not ObjectDB.objects.filter(pk=self.backward.pk).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffUnlinkRoomsAction

        result = StaffUnlinkRoomsAction().run(self.player, exit_id=self.forward.pk)
        assert not result.success
        assert ObjectDB.objects.filter(pk=self.forward.pk).exists()

    def test_refuses_to_strand_an_occupied_room(self) -> None:
        from actions.definitions.world_builder import StaffUnlinkRoomsAction

        occupant = CharacterFactory(db_key="Stranded", location=self.room_b.objectdb)
        result = StaffUnlinkRoomsAction().run(self.staff, exit_id=self.forward.pk)
        assert not result.success
        assert ObjectDB.objects.filter(pk=self.forward.pk).exists()
        assert occupant.db_location_id == self.room_b.objectdb_id

    def test_unlinks_a_dangling_one_way_exit_without_crashing(self) -> None:
        from actions.definitions.world_builder import StaffUnlinkRoomsAction

        # Null the destination directly to simulate a dangling one-way exit
        # (nullable FK) — the None side of the pair must not blow up the
        # stranding guard.
        self.forward.db_destination = None
        self.forward.save(update_fields=["db_destination"])

        result = StaffUnlinkRoomsAction().run(self.staff, exit_id=self.forward.pk)
        assert result.success
        assert not ObjectDB.objects.filter(pk=self.forward.pk).exists()


class StaffRenameExitActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("RenameExitStaff")
        self.player = _player_actor("RenameExitPlayer")
        area = AreaFactory(level=AreaLevel.WARD)
        room_a = RoomProfileFactory(area=area)
        room_b = RoomProfileFactory(area=area)
        self.forward, _backward = _exit_between(room_a.objectdb, room_b.objectdb, "North", "South")

    def test_staff_renames_exit(self) -> None:
        from actions.definitions.world_builder import StaffRenameExitAction

        result = StaffRenameExitAction().run(
            self.staff, exit_id=self.forward.pk, name="Grand Archway"
        )
        assert result.success
        self.forward.refresh_from_db()
        assert self.forward.db_key == "Grand Archway"

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffRenameExitAction

        result = StaffRenameExitAction().run(self.player, exit_id=self.forward.pk, name="Hijacked")
        assert not result.success
        self.forward.refresh_from_db()
        assert self.forward.db_key == "North"


class StaffPlaceRoomActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("PlaceRoomStaff")
        self.player = _player_actor("PlaceRoomPlayer")
        area = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=area)

    def test_staff_places_room(self) -> None:
        from actions.definitions.world_builder import StaffPlaceRoomAction

        result = StaffPlaceRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, grid_x=3, grid_y=4
        )
        assert result.success
        self.profile.refresh_from_db()
        assert (self.profile.grid_x, self.profile.grid_y) == (3, 4)

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffPlaceRoomAction

        result = StaffPlaceRoomAction().run(
            self.player, room_id=self.profile.objectdb_id, grid_x=3, grid_y=4
        )
        assert not result.success
        self.profile.refresh_from_db()
        assert self.profile.grid_x is None


class StaffRemoveRoomActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("RemoveRoomStaff")
        self.player = _player_actor("RemoveRoomPlayer")
        self.area = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=self.area)

    def test_staff_removes_room(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        room_id = self.profile.objectdb_id
        result = StaffRemoveRoomAction().run(self.staff, room_id=room_id)
        assert result.success
        assert not RoomProfile.objects.filter(objectdb_id=room_id).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        room_id = self.profile.objectdb_id
        result = StaffRemoveRoomAction().run(self.player, room_id=room_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=room_id).exists()

    def test_remove_of_exported_room_fails(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        self.profile.origin = GridOrigin.AUTHORED
        self.profile.fixture_key = "some-ward/exported-room"
        self.profile.save()
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

    def test_occupied_room_refused(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        CharacterFactory(db_key="Occupant", location=self.profile.objectdb)
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

    def test_room_with_item_contents_refused(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        ObjectDBFactory(
            db_key="Loose Chair",
            db_typeclass_path="typeclasses.objects.Object",
            location=self.profile.objectdb,
        )
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

    def test_room_with_feature_instance_refused(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomAction

        RoomFeatureInstanceFactory(room_profile=self.profile)
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()


class PromoteRoomActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("PromoteRoomStaff")
        self.player = _player_actor("PromoteRoomPlayer")
        self.area = AreaFactory(
            name="Arx City", level=AreaLevel.CITY, origin=GridOrigin.AUTHORED, slug="arx-city"
        )
        self.profile = RoomProfileFactory(area=self.area)
        self.profile.objectdb.db_key = "Golden Hart Taproom"
        self.profile.objectdb.save(update_fields=["db_key"])

    def test_staff_promotes_room(self) -> None:
        from actions.definitions.world_builder import PromoteRoomAction

        result = PromoteRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert result.success
        self.profile.refresh_from_db()
        assert self.profile.origin == GridOrigin.AUTHORED
        assert self.profile.fixture_key == "arx-city/golden-hart-taproom"

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import PromoteRoomAction

        result = PromoteRoomAction().run(self.player, room_id=self.profile.objectdb_id)
        assert not result.success
        self.profile.refresh_from_db()
        assert self.profile.fixture_key is None


class PromoteAreaActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("PromoteAreaStaff")
        self.player = _player_actor("PromoteAreaPlayer")
        self.area = AreaFactory(name="Golden Ward", level=AreaLevel.WARD)

    def test_staff_promotes_area(self) -> None:
        from actions.definitions.world_builder import PromoteAreaAction

        result = PromoteAreaAction().run(self.staff, area_id=self.area.pk)
        assert result.success
        self.area.refresh_from_db()
        assert self.area.origin == GridOrigin.AUTHORED
        assert self.area.slug == "golden-ward"

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import PromoteAreaAction

        result = PromoteAreaAction().run(self.player, area_id=self.area.pk)
        assert not result.success
        self.area.refresh_from_db()
        assert self.area.slug is None


class StaffPlaceClueActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("PlaceClueStaff")
        self.player = _player_actor("PlaceCluePlayer")
        self.room_profile = RoomProfileFactory()
        self.clue = ClueFactory(slug="torn-letter")

    def test_creates_room_clue(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue").run(
            self.staff,
            room_id=self.room_profile.objectdb_id,
            clue_slug="torn-letter",
            detect_difficulty=5,
        )

        assert result.success, result.message
        room_clue = RoomClue.objects.get(room_profile=self.room_profile, clue=self.clue)
        assert room_clue.detect_difficulty == 5
        assert room_clue.fixture_key == f"room-{self.room_profile.objectdb_id}/torn-letter"

    def test_non_staff_rejected(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue").run(
            self.player, room_id=self.room_profile.objectdb_id, clue_slug="torn-letter"
        )
        assert not result.success
        assert not RoomClue.objects.filter(room_profile=self.room_profile).exists()

    def test_fails_for_unknown_room(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue").run(
            self.staff, room_id=999999, clue_slug="torn-letter"
        )
        assert not result.success

    def test_fails_for_unknown_clue_slug(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue").run(
            self.staff, room_id=self.room_profile.objectdb_id, clue_slug="no-such-slug"
        )
        assert not result.success

    def test_re_placing_same_clue_in_same_room_updates_instead_of_erroring(self) -> None:
        from actions.registry import get_action

        get_action("staff_place_clue").run(
            self.staff,
            room_id=self.room_profile.objectdb_id,
            clue_slug="torn-letter",
            detect_difficulty=5,
        )
        result = get_action("staff_place_clue").run(
            self.staff,
            room_id=self.room_profile.objectdb_id,
            clue_slug="torn-letter",
            detect_difficulty=8,
        )
        assert result.success, result.message
        assert RoomClue.objects.filter(room_profile=self.room_profile, clue=self.clue).count() == 1
        room_clue = RoomClue.objects.get(room_profile=self.room_profile, clue=self.clue)
        assert room_clue.detect_difficulty == 8


class StaffRemoveClueActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("RemoveClueStaff")
        self.player = _player_actor("RemoveCluePlayer")

    def test_deletes_room_clue(self) -> None:
        from actions.registry import get_action

        room_clue = RoomClueFactory()
        result = get_action("staff_remove_clue").run(self.staff, room_clue_id=room_clue.pk)

        assert result.success, result.message
        assert not RoomClue.objects.filter(pk=room_clue.pk).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.registry import get_action

        room_clue = RoomClueFactory()
        result = get_action("staff_remove_clue").run(self.player, room_clue_id=room_clue.pk)

        assert not result.success
        assert RoomClue.objects.filter(pk=room_clue.pk).exists()

    def test_fails_for_unknown_room_clue(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_remove_clue").run(self.staff, room_clue_id=999999)
        assert not result.success


class StaffPlaceClueTriggerActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("PlaceClueTriggerStaff")
        self.player = _player_actor("PlaceClueTriggerPlayer")
        self.room_profile = RoomProfileFactory()
        self.clue = ClueFactory(slug="whisper")

    def test_creates_clue_trigger(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue_trigger").run(
            self.staff, room_id=self.room_profile.objectdb_id, clue_slug="whisper"
        )

        assert result.success, result.message
        trigger = ClueTrigger.objects.get(room_profile=self.room_profile, clue=self.clue)
        assert trigger.fixture_key == f"room-{self.room_profile.objectdb_id}/trigger-whisper"

    def test_non_staff_rejected(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue_trigger").run(
            self.player, room_id=self.room_profile.objectdb_id, clue_slug="whisper"
        )
        assert not result.success
        assert not ClueTrigger.objects.filter(room_profile=self.room_profile).exists()

    def test_fails_for_unknown_room(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue_trigger").run(
            self.staff, room_id=999999, clue_slug="whisper"
        )
        assert not result.success

    def test_fails_for_unknown_clue_slug(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_place_clue_trigger").run(
            self.staff, room_id=self.room_profile.objectdb_id, clue_slug="no-such-slug"
        )
        assert not result.success

    def test_re_placing_same_trigger_in_same_room_updates_instead_of_erroring(self) -> None:
        from actions.registry import get_action

        get_action("staff_place_clue_trigger").run(
            self.staff, room_id=self.room_profile.objectdb_id, clue_slug="whisper"
        )
        result = get_action("staff_place_clue_trigger").run(
            self.staff, room_id=self.room_profile.objectdb_id, clue_slug="whisper"
        )
        assert result.success, result.message
        assert (
            ClueTrigger.objects.filter(room_profile=self.room_profile, clue=self.clue).count() == 1
        )


class StaffRemoveClueTriggerActionTests(TestCase):
    def setUp(self) -> None:
        self.staff = _staff_actor("RemoveClueTriggerStaff")
        self.player = _player_actor("RemoveClueTriggerPlayer")

    def test_deletes_clue_trigger(self) -> None:
        from actions.registry import get_action

        trigger = ClueTriggerFactory()
        result = get_action("staff_remove_clue_trigger").run(self.staff, clue_trigger_id=trigger.pk)

        assert result.success, result.message
        assert not ClueTrigger.objects.filter(pk=trigger.pk).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.registry import get_action

        trigger = ClueTriggerFactory()
        result = get_action("staff_remove_clue_trigger").run(
            self.player, clue_trigger_id=trigger.pk
        )

        assert not result.success
        assert ClueTrigger.objects.filter(pk=trigger.pk).exists()

    def test_fails_for_unknown_clue_trigger(self) -> None:
        from actions.registry import get_action

        result = get_action("staff_remove_clue_trigger").run(self.staff, clue_trigger_id=999999)
        assert not result.success


class StaffPlacePortalAnchorActionTests(TestCase):
    def test_installs_anchor(self) -> None:
        from actions.registry import get_action

        staff_char = _staff_actor("PlacePortalAnchorStaff")
        room_profile = RoomProfileFactory()
        kind = PortalAnchorKindFactory(name="Mirror")

        result = get_action("staff_place_portal_anchor").run(
            staff_char,
            room_id=room_profile.objectdb_id,
            kind_name="Mirror",
            name="a tall silvered mirror",
        )

        self.assertTrue(result.success, result.message)
        self.assertTrue(
            PortalAnchor.objects.active().filter(room_profile=room_profile, kind=kind).exists()
        )

    def test_fails_for_unknown_kind(self) -> None:
        from actions.registry import get_action

        staff_char = _staff_actor("PlacePortalAnchorNoKindStaff")
        room_profile = RoomProfileFactory()

        result = get_action("staff_place_portal_anchor").run(
            staff_char, room_id=room_profile.objectdb_id, kind_name="No Such Kind", name="x"
        )
        self.assertFalse(result.success)

    def test_fails_for_duplicate_active_kind(self) -> None:
        from actions.registry import get_action

        staff_char = _staff_actor("PlacePortalAnchorDupeStaff")
        room_profile = RoomProfileFactory()
        kind = PortalAnchorKindFactory(name="Mirror")
        PortalAnchorFactory(room_profile=room_profile, kind=kind)

        result = get_action("staff_place_portal_anchor").run(
            staff_char, room_id=room_profile.objectdb_id, kind_name="Mirror", name="another"
        )
        self.assertFalse(result.success)


class StaffRemovePortalAnchorActionTests(TestCase):
    def test_dissolves_anchor(self) -> None:
        from actions.registry import get_action

        staff_char = _staff_actor("RemovePortalAnchorStaff")
        anchor = PortalAnchorFactory()

        result = get_action("staff_remove_portal_anchor").run(staff_char, anchor_id=anchor.pk)

        self.assertTrue(result.success, result.message)
        anchor.refresh_from_db()
        self.assertIsNotNone(anchor.dissolved_at)
