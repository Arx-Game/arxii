"""Tests for the GM story-builder actions (#2450).

Mirrors ``test_world_builder_actions.py``'s helper shape: one ``.run()``
success test per action (plain-int kwargs, the REST dispatch shape, #2163)
plus the invariant cases the task brief calls out by name — cap refusals,
cross-GM ownership refusals, and the staff bypass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.factories import AreaFactory
from world.areas.grid_services import create_exit_pair
from world.areas.models import Area
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, StoryAreaFactory, seed_default_gm_level_caps
from world.gm.models import StoryArea
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

if TYPE_CHECKING:
    from world.gm.models import GMProfile


def _staff_actor(db_key: str) -> ObjectDB:
    """A Character whose account is staff, with a working CharacterSheet+persona."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    CharacterSheetFactory(character=char)
    return char


def _player_actor(db_key: str) -> ObjectDB:
    """A Character whose account is NOT staff and has no GMProfile."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=False)
    char.db_account = account
    char.save()
    CharacterSheetFactory(character=char)
    return char


def _gm_actor(db_key: str) -> tuple[ObjectDB, GMProfile]:
    """A Character whose account is a non-staff, STARTING-level GM.

    ``MinimumGMLevelPrerequisite`` (and ``_gm_profile_for``) resolve the GM
    account via ``actor.active_account`` -> ``sheet_data.roster_entry.
    current_tenure.player_data.account`` -- a bare ``char.db_account`` (the
    world_builder staff-test shortcut, which ``StaffOnlyPrerequisite`` reads
    directly) does not wire that up. Mirrors ``_pc_in_room`` in
    ``test_gm_adjudication_actions.py``.
    """
    char = CharacterFactory(db_key=db_key)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    profile: GMProfile = GMProfileFactory(account=account)
    return char, profile


class CreateStoryAreaActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("CreateStoryAreaGM")
        self.player = _player_actor("CreateStoryAreaPlayer")

    def test_gm_creates_area(self) -> None:
        from actions.definitions.story_builder import CreateStoryAreaAction

        result = CreateStoryAreaAction().run(
            self.gm_actor, name="The Sunken Crypt", description="Dank and forgotten."
        )
        assert result.success
        area = Area.objects.get(name="The Sunken Crypt")
        assert area.origin == GridOrigin.STORY
        assert StoryArea.objects.filter(area=area, gm=self.gm_profile).exists()

    def test_plain_player_rejected(self) -> None:
        from actions.definitions.story_builder import CreateStoryAreaAction

        result = CreateStoryAreaAction().run(self.player, name="Should Not Exist")
        assert not result.success
        assert not Area.objects.filter(name="Should Not Exist").exists()

    def test_create_fails_at_cap(self) -> None:
        from actions.definitions.story_builder import CreateStoryAreaAction

        # STARTING cap is 1 story area.
        StoryAreaFactory(gm=self.gm_profile)
        result = CreateStoryAreaAction().run(self.gm_actor, name="Second Area")
        assert not result.success
        assert not Area.objects.filter(name="Second Area").exists()


class EditStoryAreaActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("EditStoryAreaGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)

    def test_gm_edits_own_area(self) -> None:
        from actions.definitions.story_builder import EditStoryAreaAction

        result = EditStoryAreaAction().run(
            self.gm_actor, area_id=self.story.area_id, name="Renamed Area"
        )
        assert result.success
        self.story.area.refresh_from_db()
        assert self.story.area.name == "Renamed Area"

    def test_foreign_gm_rejected(self) -> None:
        from actions.definitions.story_builder import EditStoryAreaAction

        other_gm_actor, _ = _gm_actor("EditStoryAreaOtherGM")
        result = EditStoryAreaAction().run(
            other_gm_actor, area_id=self.story.area_id, name="Hijacked"
        )
        assert not result.success
        raw_name = Area.objects.filter(pk=self.story.area_id).values_list("name", flat=True).first()
        assert raw_name != "Hijacked"


class RemoveStoryAreaActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("RemoveStoryAreaGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)

    def test_gm_removes_empty_area(self) -> None:
        from actions.definitions.story_builder import RemoveStoryAreaAction

        area_id = self.story.area_id
        result = RemoveStoryAreaAction().run(self.gm_actor, area_id=area_id)
        assert result.success
        assert not Area.objects.filter(pk=area_id).exists()

    def test_remove_refuses_when_rooms_exist(self) -> None:
        from actions.definitions.story_builder import RemoveStoryAreaAction

        RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        result = RemoveStoryAreaAction().run(self.gm_actor, area_id=self.story.area_id)
        assert not result.success
        assert Area.objects.filter(pk=self.story.area_id).exists()


class StoryDigRoomActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("StoryDigRoomGM")
        self.staff = _staff_actor("StoryDigRoomStaff")
        self.story = StoryAreaFactory(gm=self.gm_profile)

    def test_gm_digs_room_forces_story_shape(self) -> None:
        from actions.definitions.story_builder import StoryDigRoomAction

        result = StoryDigRoomAction().run(
            self.gm_actor, area_id=self.story.area_id, name="Torture Chamber"
        )
        assert result.success
        profile = RoomProfile.objects.get(area=self.story.area, objectdb__db_key="Torture Chamber")
        assert profile.origin == GridOrigin.STORY
        assert profile.is_public is False
        assert profile.fixture_key is None

    def test_dig_fails_at_room_cap(self) -> None:
        from actions.definitions.story_builder import StoryDigRoomAction

        # STARTING cap is 8 rooms per story area.
        for _ in range(8):
            RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        result = StoryDigRoomAction().run(
            self.gm_actor, area_id=self.story.area_id, name="One Too Many"
        )
        assert not result.success
        assert not RoomProfile.objects.filter(
            area=self.story.area, objectdb__db_key="One Too Many"
        ).exists()

    def test_dig_into_foreign_gm_area_fails(self) -> None:
        from actions.definitions.story_builder import StoryDigRoomAction

        other_gm_actor, _ = _gm_actor("StoryDigRoomOtherGM")
        result = StoryDigRoomAction().run(
            other_gm_actor, area_id=self.story.area_id, name="Should Not Exist"
        )
        assert not result.success
        assert not RoomProfile.objects.filter(
            area=self.story.area, objectdb__db_key="Should Not Exist"
        ).exists()

    def test_staff_can_dig_into_any_story_area(self) -> None:
        from actions.definitions.story_builder import StoryDigRoomAction

        result = StoryDigRoomAction().run(
            self.staff, area_id=self.story.area_id, name="Staff Dug Room"
        )
        assert result.success
        profile = RoomProfile.objects.get(area=self.story.area, objectdb__db_key="Staff Dug Room")
        assert profile.origin == GridOrigin.STORY
        assert profile.is_public is False


class StoryEditRoomActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("StoryEditRoomGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)
        self.profile = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)

    def test_edit_room_renames(self) -> None:
        from actions.definitions.story_builder import StoryEditRoomAction

        result = StoryEditRoomAction().run(
            self.gm_actor,
            room_id=self.profile.objectdb_id,
            name="The Iron Cell",
            description="Cold stone, dim light.",
        )
        assert result.success
        display = ObjectDisplayData.objects.get(object=self.profile.objectdb)
        assert display.longname == "The Iron Cell"
        assert display.permanent_description == "Cold stone, dim light."

    def test_foreign_gm_rejected(self) -> None:
        from actions.definitions.story_builder import StoryEditRoomAction

        other_gm_actor, _ = _gm_actor("StoryEditRoomOtherGM")
        result = StoryEditRoomAction().run(
            other_gm_actor, room_id=self.profile.objectdb_id, name="Hijacked"
        )
        assert not result.success
        assert not ObjectDisplayData.objects.filter(
            object=self.profile.objectdb, longname="Hijacked"
        ).exists()


class StoryLinkRoomsActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("LinkRoomsGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)
        self.room_a = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        self.room_b = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)

    def test_gm_links_own_story_rooms(self) -> None:
        from actions.definitions.story_builder import StoryLinkRoomsAction

        result = StoryLinkRoomsAction().run(
            self.gm_actor,
            room_a_id=self.room_a.objectdb_id,
            room_b_id=self.room_b.objectdb_id,
            name="North Door",
            reverse_name="South Door",
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

    def test_link_to_canonical_room_fails(self) -> None:
        from actions.definitions.story_builder import StoryLinkRoomsAction

        canonical_area = AreaFactory(level=AreaLevel.WARD)
        canonical_room = RoomProfileFactory(area=canonical_area, origin=GridOrigin.AUTHORED)
        result = StoryLinkRoomsAction().run(
            self.gm_actor,
            room_a_id=self.room_a.objectdb_id,
            room_b_id=canonical_room.objectdb_id,
            name="North Door",
            reverse_name="South Door",
        )
        assert not result.success
        assert not ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit", db_location=self.room_a.objectdb
        ).exists()

    def test_link_to_foreign_gm_room_fails(self) -> None:
        from actions.definitions.story_builder import StoryLinkRoomsAction

        _other_gm_actor, other_gm_profile = _gm_actor("LinkRoomsOtherGM")
        other_story = StoryAreaFactory(gm=other_gm_profile)
        other_room = RoomProfileFactory(area=other_story.area, origin=GridOrigin.STORY)
        result = StoryLinkRoomsAction().run(
            self.gm_actor,
            room_a_id=self.room_a.objectdb_id,
            room_b_id=other_room.objectdb_id,
            name="North Door",
            reverse_name="South Door",
        )
        assert not result.success
        assert not ObjectDB.objects.filter(
            db_typeclass_path="typeclasses.exits.Exit", db_location=self.room_a.objectdb
        ).exists()


class StoryUnlinkRoomsActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("UnlinkRoomsGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)
        self.room_a = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        self.room_b = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        self.forward, self.backward = create_exit_pair(
            name="North",
            aliases=(),
            reverse_name="South",
            reverse_aliases=(),
            room_a=self.room_a.objectdb,
            room_b=self.room_b.objectdb,
        )

    def test_gm_unlinks_own_story_rooms(self) -> None:
        from actions.definitions.story_builder import StoryUnlinkRoomsAction

        result = StoryUnlinkRoomsAction().run(self.gm_actor, exit_id=self.forward.pk)
        assert result.success
        assert not ObjectDB.objects.filter(pk=self.forward.pk).exists()
        assert not ObjectDB.objects.filter(pk=self.backward.pk).exists()

    def test_refuses_to_strand_an_occupied_room(self) -> None:
        from actions.definitions.story_builder import StoryUnlinkRoomsAction

        occupant = CharacterFactory(db_key="StoryStranded", location=self.room_b.objectdb)
        result = StoryUnlinkRoomsAction().run(self.gm_actor, exit_id=self.forward.pk)
        assert not result.success
        assert ObjectDB.objects.filter(pk=self.forward.pk).exists()
        assert occupant.db_location_id == self.room_b.objectdb_id


class StoryPlaceRoomActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("PlaceRoomGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)
        self.profile = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)

    def test_gm_moves_own_room(self) -> None:
        from actions.definitions.story_builder import StoryPlaceRoomAction

        result = StoryPlaceRoomAction().run(
            self.gm_actor, room_id=self.profile.objectdb_id, grid_x=3, grid_y=4
        )
        assert result.success
        self.profile.refresh_from_db()
        assert (self.profile.grid_x, self.profile.grid_y) == (3, 4)

    def test_foreign_gm_rejected(self) -> None:
        from actions.definitions.story_builder import StoryPlaceRoomAction

        other_gm_actor, _ = _gm_actor("PlaceRoomOtherGM")
        result = StoryPlaceRoomAction().run(
            other_gm_actor, room_id=self.profile.objectdb_id, grid_x=3, grid_y=4
        )
        assert not result.success
        self.profile.refresh_from_db()
        assert self.profile.grid_x is None


class StoryRemoveRoomActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.gm_actor, self.gm_profile = _gm_actor("RemoveRoomGM")
        self.story = StoryAreaFactory(gm=self.gm_profile)
        self.profile = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)

    def test_story_room_has_no_fixture_key_by_construction(self) -> None:
        assert self.profile.fixture_key is None
        assert self.profile.origin == GridOrigin.STORY

    def test_gm_removes_own_empty_room(self) -> None:
        from actions.definitions.story_builder import StoryRemoveRoomAction

        room_id = self.profile.objectdb_id
        result = StoryRemoveRoomAction().run(self.gm_actor, room_id=room_id)
        assert result.success
        assert not RoomProfile.objects.filter(objectdb_id=room_id).exists()

    def test_occupied_room_refused(self) -> None:
        from actions.definitions.story_builder import StoryRemoveRoomAction

        CharacterFactory(db_key="StoryOccupant", location=self.profile.objectdb)
        result = StoryRemoveRoomAction().run(self.gm_actor, room_id=self.profile.objectdb_id)
        assert not result.success
        assert RoomProfile.objects.filter(objectdb_id=self.profile.objectdb_id).exists()

    def test_remove_deletes_room_and_exits(self) -> None:
        from actions.definitions.story_builder import StoryRemoveRoomAction

        other_room = RoomProfileFactory(area=self.story.area, origin=GridOrigin.STORY)
        forward, backward = create_exit_pair(
            name="North",
            aliases=(),
            reverse_name="South",
            reverse_aliases=(),
            room_a=self.profile.objectdb,
            room_b=other_room.objectdb,
        )
        room_id = self.profile.objectdb_id
        result = StoryRemoveRoomAction().run(self.gm_actor, room_id=room_id)
        assert result.success
        assert not RoomProfile.objects.filter(objectdb_id=room_id).exists()
        assert not ObjectDB.objects.filter(pk=forward.pk).exists()
        assert not ObjectDB.objects.filter(pk=backward.pk).exists()
        assert RoomProfile.objects.filter(objectdb_id=other_room.objectdb_id).exists()


class StoryBuilderNonGMRejectionTests(TestCase):
    """One non-GM rejects the four link/unlink/place/remove keys (#2450 task 6)."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def setUp(self) -> None:
        self.player = _player_actor("StoryBuilderRejectionPlayer")

    def test_non_gm_rejected_on_each_key(self) -> None:
        from actions.registry import get_action

        for key in (
            "story_link_rooms",
            "story_unlink_rooms",
            "story_place_room",
            "story_remove_room",
        ):
            action = get_action(key)
            assert action is not None, key
            result = action.run(self.player)
            assert not result.success, key
