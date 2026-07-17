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
from world.areas.constants import GridOrigin
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
