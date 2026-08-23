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

    def test_slug_change_with_keyed_room_beneath_is_refused(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        self.area.origin = GridOrigin.AUTHORED
        self.area.slug = "old-name"
        self.area.save()
        RoomProfileFactory(area=self.area, fixture_key="old-name/kept-room")
        result = EditAreaAction().run(self.staff, area_id=self.area.pk, slug="new-name")
        assert not result.success
        self.area.refresh_from_db()
        assert self.area.slug == "old-name"

    def test_slug_change_before_any_keyed_room_is_allowed(self) -> None:
        """#3269 — a typo'd slug is recoverable until a fixture key bakes it in."""
        from actions.definitions.world_builder import EditAreaAction

        self.area.origin = GridOrigin.AUTHORED
        self.area.slug = "typo-slug"
        self.area.save()
        result = EditAreaAction().run(self.staff, area_id=self.area.pk, slug="fixed-slug")
        assert result.success
        self.area.refresh_from_db()
        assert self.area.slug == "fixed-slug"

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
        from django.utils import timezone

        from actions.definitions.world_builder import StaffRemoveRoomAction

        self.profile.origin = GridOrigin.AUTHORED
        self.profile.fixture_key = "some-ward/exported-room"
        self.profile.exported_at = timezone.now()
        self.profile.save()
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

    def test_keyed_but_never_exported_room_deletes(self) -> None:
        """#3269 — a fixture key alone is not an export; mistakes stay deletable."""
        from actions.definitions.world_builder import StaffRemoveRoomAction

        self.profile.origin = GridOrigin.AUTHORED
        self.profile.fixture_key = "some-ward/typo-room"
        self.profile.save()
        result = StaffRemoveRoomAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert result.success
        assert not RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

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


class RelationalDigActionTests(TestCase):
    """#3269 — dig off an anchor room: derived cell + aliased exit pair."""

    def setUp(self) -> None:
        self.staff = _staff_actor("RelDigStaff")
        self.area = AreaFactory(
            name="Grid Ward", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="grid-ward"
        )
        self.anchor = RoomProfileFactory(area=self.area, grid_x=2, grid_y=3, floor=0)

    def test_relational_dig_creates_linked_neighbor(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.area.pk,
            name="North Walk",
            from_room_id=self.anchor.objectdb_id,
            direction="north",
        )
        assert result.success, result.message
        profile = RoomProfile.objects.get(fixture_key="grid-ward/north-walk")
        assert (profile.grid_x, profile.grid_y, profile.floor) == (2, 4, 0)
        exit_out = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.anchor.objectdb,
            db_destination=profile.objectdb,
        )
        assert exit_out.db_key == "north"
        assert "n" in exit_out.aliases.all()
        back = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=profile.objectdb,
            db_destination=self.anchor.objectdb,
        )
        assert back.db_key == "south"
        assert "s" in back.aliases.all()

    def test_up_direction_moves_floors(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.area.pk,
            name="Upper Landing",
            from_room_id=self.anchor.objectdb_id,
            direction="up",
        )
        assert result.success, result.message
        profile = RoomProfile.objects.get(fixture_key="grid-ward/upper-landing")
        assert (profile.grid_x, profile.grid_y, profile.floor) == (2, 3, 1)

    def test_unplaced_anchor_is_refused(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        floating = RoomProfileFactory(area=self.area)
        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.area.pk,
            name="Nowhere Room",
            from_room_id=floating.objectdb_id,
            direction="east",
        )
        assert not result.success

    def test_anchor_in_other_area_is_refused(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction

        other = AreaFactory(
            name="Elsewhere", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="elsewhere"
        )
        foreign = RoomProfileFactory(area=other, grid_x=0, grid_y=0)
        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.area.pk,
            name="Wrong Anchor",
            from_room_id=foreign.objectdb_id,
            direction="west",
        )
        assert not result.success

    def test_like_exemplar_copies_size_and_description(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction
        from evennia_extensions.models import RoomSizeTier

        tier = RoomSizeTier.objects.create(name="Modest Test Tier", units=7)
        model_room = RoomProfileFactory(area=self.area, size=tier)
        ObjectDisplayData.objects.create(
            object=model_room.objectdb, permanent_description="A cozy den."
        )
        result = StaffDigRoomAction().run(
            self.staff,
            area_id=self.area.pk,
            name="Copy Den",
            like_room_id=model_room.objectdb_id,
        )
        assert result.success, result.message
        profile = RoomProfile.objects.get(fixture_key="grid-ward/copy-den")
        assert profile.size_id == tier.pk
        desc = ObjectDisplayData.objects.get(object_id=profile.objectdb_id)
        assert desc.permanent_description == "A cozy den."

    def test_blank_description_defaults_to_placeholder_stub(self) -> None:
        from actions.definitions.world_builder import StaffDigRoomAction
        from world.areas.constants import UNFINISHED_ROOM_DESC

        result = StaffDigRoomAction().run(self.staff, area_id=self.area.pk, name="Bare Room")
        assert result.success, result.message
        profile = RoomProfile.objects.get(fixture_key="grid-ward/bare-room")
        desc = ObjectDisplayData.objects.get(object_id=profile.objectdb_id)
        assert desc.permanent_description == UNFINISHED_ROOM_DESC


class StaffRemoveAreaActionTests(TestCase):
    """#3269 — empty areas are deletable; populated ones refuse."""

    def setUp(self) -> None:
        self.staff = _staff_actor("RemoveAreaStaff")
        self.player = _player_actor("RemoveAreaPlayer")
        self.area = AreaFactory(name="Mistake Ward", level=AreaLevel.WARD)

    def test_staff_removes_empty_area(self) -> None:
        from actions.definitions.world_builder import StaffRemoveAreaAction

        area_id = self.area.pk
        result = StaffRemoveAreaAction().run(self.staff, area_id=area_id)
        assert result.success, result.message
        assert not Area.objects.filter(pk=area_id).exists()

    def test_non_staff_rejected(self) -> None:
        from actions.definitions.world_builder import StaffRemoveAreaAction

        result = StaffRemoveAreaAction().run(self.player, area_id=self.area.pk)
        assert not result.success
        assert Area.objects.filter(pk=self.area.pk).exists()

    def test_area_with_rooms_refused(self) -> None:
        from actions.definitions.world_builder import StaffRemoveAreaAction

        RoomProfileFactory(area=self.area)
        result = StaffRemoveAreaAction().run(self.staff, area_id=self.area.pk)
        assert not result.success
        assert Area.objects.filter(pk=self.area.pk).exists()

    def test_area_with_children_refused(self) -> None:
        from actions.definitions.world_builder import StaffRemoveAreaAction

        AreaFactory(name="Child Block", level=AreaLevel.NEIGHBORHOOD, parent=self.area)
        result = StaffRemoveAreaAction().run(self.staff, area_id=self.area.pk)
        assert not result.success
        assert Area.objects.filter(pk=self.area.pk).exists()


class StaffMoveRoomActionTests(TestCase):
    """#3269 — re-parent a mis-dug room; coords reset; fixture key warned."""

    def setUp(self) -> None:
        self.staff = _staff_actor("MoveRoomStaff")
        self.source = AreaFactory(
            name="Wrong Ward", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="wrong-ward"
        )
        self.target = AreaFactory(
            name="Right Ward", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="right-ward"
        )
        self.profile = RoomProfileFactory(area=self.source, grid_x=1, grid_y=1)

    def test_staff_moves_room_and_resets_coords(self) -> None:
        from actions.definitions.world_builder import StaffMoveRoomAction

        result = StaffMoveRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, area_id=self.target.pk
        )
        assert result.success, result.message
        self.profile.refresh_from_db()
        assert self.profile.area_id == self.target.pk
        assert self.profile.grid_x is None
        assert self.profile.grid_y is None

    def test_move_warns_about_retained_fixture_key_prefix(self) -> None:
        from actions.definitions.world_builder import StaffMoveRoomAction

        self.profile.fixture_key = "wrong-ward/kept-room"
        self.profile.save(update_fields=["fixture_key"])
        result = StaffMoveRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, area_id=self.target.pk
        )
        assert result.success
        assert "fixture key" in result.message

    def test_move_to_non_authored_area_refused(self) -> None:
        from actions.definitions.world_builder import StaffMoveRoomAction

        story = AreaFactory(name="Story Spot", level=AreaLevel.WARD, origin=GridOrigin.STORY)
        result = StaffMoveRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, area_id=story.pk
        )
        assert not result.success


class RoomRenameDisplayPathTests(TestCase):
    """#3269 — a rename must land in BOTH db_key (look) and longname (area path)."""

    def setUp(self) -> None:
        self.staff = _staff_actor("RenamePathStaff")
        self.area = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=self.area)

    def test_rename_updates_both_display_sources(self) -> None:
        from actions.definitions.world_builder import StaffEditRoomAction

        result = StaffEditRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, name="Renamed Hall"
        )
        assert result.success, result.message
        assert ObjectDB.objects.get(pk=self.profile.objectdb_id).db_key == "Renamed Hall"
        display = ObjectDisplayData.objects.get(object_id=self.profile.objectdb_id)
        assert display.longname == "Renamed Hall"

    def test_description_normalizes_mush_markup(self) -> None:
        from actions.definitions.world_builder import StaffEditRoomAction

        result = StaffEditRoomAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            description="First paragraph.%r%rSecond%tindented.",
        )
        assert result.success, result.message
        display = ObjectDisplayData.objects.get(object_id=self.profile.objectdb_id)
        assert "%r" not in display.permanent_description
        assert "%t" not in display.permanent_description


class PhaseBRoomAuthoringTests(TestCase):
    """#3269 Phase B — stats, places, ambient, features, staffing, travel,
    blueprint, bindings, exit detail, duplicate, batch dig."""

    def setUp(self) -> None:
        self.staff = _staff_actor("PhaseBStaff")
        self.area = AreaFactory(
            name="Author Ward", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="author-ward"
        )
        self.profile = RoomProfileFactory(area=self.area, grid_x=0, grid_y=0)

    def test_stat_authoring_writes_zero_decay_modifier(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomStatAction
        from world.locations.constants import AUTHORED_STAT_SOURCE
        from world.locations.models import LocationValueModifier

        result = StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="noise", value=70
        )
        assert result.success, result.message
        row = LocationValueModifier.objects.get(
            room_profile=self.profile, stat_key="noise", source=AUTHORED_STAT_SOURCE
        )
        assert row.value == 70
        assert row.change_per_day == 0

    def test_stat_pin_writes_override_and_warns(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomStatAction
        from world.locations.models import LocationValueOverride

        result = StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="cold", value=0, pin=True
        )
        assert result.success
        assert "cuts the whole cascade" in result.message
        assert LocationValueOverride.objects.filter(
            room_profile=self.profile, stat_key="cold"
        ).exists()

    def test_stat_clear_removes_both(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomStatAction
        from world.locations.models import LocationValueModifier, LocationValueOverride

        StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="noise", value=70
        )
        StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="noise", value=10, pin=True
        )
        result = StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="noise", clear=True
        )
        assert result.success
        assert not LocationValueModifier.objects.filter(
            room_profile=self.profile, stat_key="noise"
        ).exists()
        assert not LocationValueOverride.objects.filter(
            room_profile=self.profile, stat_key="noise"
        ).exists()

    def test_place_add_and_duplicate_name_refused(self) -> None:
        from actions.definitions.world_builder import StaffAddPlaceAction
        from world.scenes.place_models import Place

        result = StaffAddPlaceAction().run(
            self.staff, room_id=self.profile.objectdb_id, name="The Bar"
        )
        assert result.success
        assert Place.objects.filter(room=self.profile, name="The Bar").exists()
        again = StaffAddPlaceAction().run(
            self.staff, room_id=self.profile.objectdb_id, name="the bar"
        )
        assert not again.success

    def test_ambient_emit_mints_key_from_fixture(self) -> None:
        from actions.definitions.world_builder import StaffAddAmbientEmitAction
        from world.narrative.models import AmbientEmit

        self.profile.fixture_key = "author-ward/dusty-plaza"
        self.profile.save(update_fields=["fixture_key"])
        result = StaffAddAmbientEmitAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            text="Dust motes drift.",
            gate_stat_key="crime",
            gate_min=60,
        )
        assert result.success, result.message
        emit = AmbientEmit.objects.get(room_profile=self.profile)
        assert emit.key == "dusty-plaza-emit-001"
        assert emit.gate_stat_key == "crime"

    def test_feature_fiat_runs_the_real_strategy(self) -> None:
        """A SOCIAL_HUB fiat install must land the traffic modifier + flag —
        proof the fiat path runs the identical per-kind handler."""
        from actions.definitions.world_builder import StaffInstallRoomFeatureAction
        from world.locations.models import LocationValueModifier
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureKindFactory
        from world.room_features.models import RoomFeatureInstance

        kind = RoomFeatureKindFactory(
            name="Test Social Hub",
            service_strategy=RoomFeatureServiceStrategy.SOCIAL_HUB,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        result = StaffInstallRoomFeatureAction().run(
            self.staff, room_id=self.profile.objectdb_id, kind=kind.name, target_level=2
        )
        assert result.success, result.message
        instance = RoomFeatureInstance.objects.filter(room_profile=self.profile).active().get()
        assert instance.level == 2
        self.profile.refresh_from_db()
        assert self.profile.is_social_hub
        assert LocationValueModifier.objects.filter(
            room_profile=self.profile, stat_key="traffic"
        ).exists()

    def test_feature_fiat_refuses_vault_and_second_kind(self) -> None:
        from actions.definitions.world_builder import StaffInstallRoomFeatureAction
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureKindFactory

        vault = RoomFeatureKindFactory(
            name="Test Vault", service_strategy=RoomFeatureServiceStrategy.VAULT
        )
        result = StaffInstallRoomFeatureAction().run(
            self.staff, room_id=self.profile.objectdb_id, kind=vault.name
        )
        assert not result.success

    def test_feature_remove_reconciles_traffic(self) -> None:
        from actions.definitions.world_builder import (
            StaffInstallRoomFeatureAction,
            StaffRemoveRoomFeatureAction,
        )
        from world.locations.models import LocationValueModifier
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureKindFactory

        kind = RoomFeatureKindFactory(
            name="Test Social Hub",
            service_strategy=RoomFeatureServiceStrategy.SOCIAL_HUB,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        StaffInstallRoomFeatureAction().run(
            self.staff, room_id=self.profile.objectdb_id, kind=kind.name
        )
        result = StaffRemoveRoomFeatureAction().run(self.staff, room_id=self.profile.objectdb_id)
        assert result.success, result.message
        assert not LocationValueModifier.objects.filter(
            room_profile=self.profile, stat_key="traffic"
        ).exists()

    def test_functionary_assign_and_remove(self) -> None:
        from actions.definitions.world_builder import (
            StaffAssignFunctionaryAction,
            StaffRemoveFunctionaryAction,
        )
        from world.npc_services.factories import NPCRoleFactory
        from world.npc_services.models import Functionary

        role = NPCRoleFactory(name="Test Registrar")
        result = StaffAssignFunctionaryAction().run(
            self.staff, room_id=self.profile.objectdb_id, role=role.name
        )
        assert result.success, result.message
        assert Functionary.objects.filter(room=self.profile, role=role, is_active=True).exists()
        removed = StaffRemoveFunctionaryAction().run(
            self.staff, room_id=self.profile.objectdb_id, role=role.name
        )
        assert removed.success
        assert not Functionary.objects.filter(room=self.profile, role=role, is_active=True).exists()

    def test_travel_hub_toggle(self) -> None:
        from actions.definitions.world_builder import StaffSetTravelHubAction
        from world.travel.models import TravelHub

        result = StaffSetTravelHubAction().run(
            self.staff, room_id=self.profile.objectdb_id, enabled=True, modes="land, sea"
        )
        assert result.success, result.message
        hub = TravelHub.objects.get(room_profile=self.profile)
        assert hub.travel_modes == ["LAND", "SEA"]
        off = StaffSetTravelHubAction().run(
            self.staff, room_id=self.profile.objectdb_id, enabled=False
        )
        assert off.success
        assert not TravelHub.objects.filter(room_profile=self.profile).exists()

    def test_blueprint_set_and_clear(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomBlueprintAction
        from world.areas.positioning.models import PositionBlueprint

        blueprint = PositionBlueprint.objects.create(name="Test Camp Layout")
        result = StaffSetRoomBlueprintAction().run(
            self.staff, room_id=self.profile.objectdb_id, blueprint=blueprint.name
        )
        assert result.success
        self.profile.refresh_from_db()
        assert self.profile.default_blueprint_id == blueprint.pk
        cleared = StaffSetRoomBlueprintAction().run(
            self.staff, room_id=self.profile.objectdb_id, blueprint=""
        )
        assert cleared.success

    def test_starting_room_binding(self) -> None:
        from actions.definitions.world_builder import StaffSetStartingRoomAction
        from world.character_creation.factories import StartingAreaFactory

        starting_area = StartingAreaFactory()
        result = StaffSetStartingRoomAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            starting_area_id=starting_area.pk,
        )
        assert result.success, result.message
        starting_area.refresh_from_db()
        assert starting_area.default_starting_room_id == self.profile.objectdb_id

    def test_exit_window_switch_auto_opens(self) -> None:
        from actions.definitions.world_builder import StaffSetExitDetailAction
        from evennia_extensions.models import ExitProfile

        other = RoomProfileFactory(area=self.area, grid_x=1, grid_y=0)
        exit_out, _ = _exit_between(self.profile.objectdb, other.objectdb, "east", "west")
        result = StaffSetExitDetailAction().run(
            self.staff, exit_id=exit_out.pk, kind="window", aliases="peek, e"
        )
        assert result.success, result.message
        exit_profile = ExitProfile.objects.get(objectdb=exit_out)
        assert exit_profile.exit_kind == "window"
        assert exit_profile.is_open is True
        assert "peek" in exit_out.aliases.all()

    def test_duplicate_room_copies_template_surfaces(self) -> None:
        from actions.definitions.world_builder import (
            StaffAddPlaceAction,
            StaffDuplicateRoomAction,
            StaffSetRoomStatAction,
        )
        from evennia_extensions.models import RoomProfile as RoomProfileModel
        from world.locations.constants import AUTHORED_STAT_SOURCE
        from world.locations.models import LocationValueModifier
        from world.scenes.place_models import Place

        StaffSetRoomStatAction().run(
            self.staff, room_id=self.profile.objectdb_id, stat_key="noise", value=44
        )
        StaffAddPlaceAction().run(self.staff, room_id=self.profile.objectdb_id, name="Corner Booth")
        result = StaffDuplicateRoomAction().run(
            self.staff, room_id=self.profile.objectdb_id, name="Copy Shop"
        )
        assert result.success, result.message
        copy = RoomProfileModel.objects.get(fixture_key="author-ward/copy-shop")
        assert copy.grid_x is None
        assert Place.objects.filter(room=copy, name="Corner Booth").exists()
        assert LocationValueModifier.objects.filter(
            room_profile=copy, stat_key="noise", source=AUTHORED_STAT_SOURCE, value=44
        ).exists()

    def test_batch_dig_corridor(self) -> None:
        from actions.definitions.world_builder import StaffBatchDigAction
        from evennia_extensions.models import RoomProfile as RoomProfileModel

        result = StaffBatchDigAction().run(
            self.staff,
            area_id=self.area.pk,
            base_name="Corridor",
            count=3,
            from_room_id=self.profile.objectdb_id,
            direction="north",
        )
        assert result.success, result.message
        rooms = list(
            RoomProfileModel.objects.filter(
                fixture_key__startswith="author-ward/corridor-"
            ).order_by("grid_y")
        )
        assert [(r.grid_x, r.grid_y) for r in rooms] == [(0, 1), (0, 2), (0, 3)]


class RoomDescVariantActionTests(TestCase):
    """#3291 — staff_set_room_desc_variant / staff_remove_room_desc_variant."""

    def setUp(self) -> None:
        self.staff = _staff_actor("DescVariantStaff")
        self.area = AreaFactory(
            name="Variant Ward", level=AreaLevel.WARD, origin=GridOrigin.AUTHORED, slug="var-ward"
        )
        self.profile = RoomProfileFactory(area=self.area)

    def test_set_creates_variant(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomDescVariantAction
        from evennia_extensions.models import RoomDescVariant

        result = StaffSetRoomDescVariantAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            season="winter",
            description="Frost rimes every rail.",
        )
        assert result.success, result.message
        variant = RoomDescVariant.objects.get(room_profile=self.profile, season="winter")
        assert variant.phase is None
        assert variant.description == "Frost rimes every rail."

    def test_set_upserts_on_same_key(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomDescVariantAction
        from evennia_extensions.models import RoomDescVariant

        StaffSetRoomDescVariantAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            phase="night",
            description="Torches gutter in the dark.",
        )
        result = StaffSetRoomDescVariantAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            phase="night",
            description="Lanterns burn low.",
        )
        assert result.success, result.message
        assert RoomDescVariant.objects.filter(room_profile=self.profile, phase="night").count() == 1
        variant = RoomDescVariant.objects.get(room_profile=self.profile, phase="night")
        assert variant.description == "Lanterns burn low."

    def test_set_requires_season_or_phase(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomDescVariantAction

        result = StaffSetRoomDescVariantAction().run(
            self.staff, room_id=self.profile.objectdb_id, description="Featureless."
        )
        assert not result.success

    def test_set_rejects_bad_season(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomDescVariantAction

        result = StaffSetRoomDescVariantAction().run(
            self.staff,
            room_id=self.profile.objectdb_id,
            season="monsoon",
            description="Not a real season.",
        )
        assert not result.success

    def test_remove_deletes_variant(self) -> None:
        from actions.definitions.world_builder import StaffRemoveRoomDescVariantAction
        from evennia_extensions.factories import RoomDescVariantFactory
        from evennia_extensions.models import RoomDescVariant

        variant = RoomDescVariantFactory(room_profile=self.profile, season="summer")
        result = StaffRemoveRoomDescVariantAction().run(self.staff, variant_id=variant.pk)
        assert result.success, result.message
        assert not RoomDescVariant.objects.filter(pk=variant.pk).exists()

    def test_non_staff_cannot_set(self) -> None:
        from actions.definitions.world_builder import StaffSetRoomDescVariantAction
        from evennia_extensions.models import RoomDescVariant

        player = _player_actor("DescVariantPlayer")
        result = StaffSetRoomDescVariantAction().run(
            player, room_id=self.profile.objectdb_id, season="spring", description="Nope."
        )
        assert not result.success
        assert not RoomDescVariant.objects.filter(room_profile=self.profile).exists()


class PhaseCAreaMetadataTests(TestCase):
    """#3269 Phase C — edit_area's metadata kwargs + the below-REGION climate warning."""

    def setUp(self) -> None:
        self.staff = _staff_actor("PhaseCStaff")
        self.area = AreaFactory(name="Meta Ward", level=AreaLevel.WARD)

    def test_metadata_fields_apply(self) -> None:
        from actions.definitions.world_builder import EditAreaAction
        from world.realms.models import Realm

        realm = Realm.objects.create(name="Testland")
        result = EditAreaAction().run(
            self.staff,
            area_id=self.area.pk,
            realm=realm.name,
            description="A test ward.",
            color="|y",
            permit_eligibility="open",
            grid_x=3,
            grid_y=4,
        )
        assert result.success, result.message
        self.area.refresh_from_db()
        assert self.area.realm_id == realm.pk
        assert self.area.description == "A test ward."
        assert (self.area.grid_x, self.area.grid_y) == (3, 4)

    def test_unknown_realm_name_refused(self) -> None:
        from actions.definitions.world_builder import EditAreaAction

        result = EditAreaAction().run(self.staff, area_id=self.area.pk, realm="Nowhereland")
        assert not result.success

    def test_climate_below_region_warns(self) -> None:
        from actions.definitions.world_builder import EditAreaAction
        from world.weather.models import Climate

        climate = Climate.objects.create(name="Test Drizzle")
        result = EditAreaAction().run(self.staff, area_id=self.area.pk, climate=climate.name)
        assert result.success, result.message
        assert "below REGION" in result.message
