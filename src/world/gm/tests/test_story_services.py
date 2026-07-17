"""story_services tests (#2450, epic #2436 slice 3).

Caps, ownership, grants, join/leave, and GM-owned temp scene rooms.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import GridOrigin
from world.areas.models import Area
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import (
    GMLevelCapFactory,
    GMProfileFactory,
    StoryAreaFactory,
    StoryRoomGrantFactory,
    seed_default_gm_level_caps,
)
from world.gm.models import GMLevelCap, StoryArea, StoryRoomGrant
from world.gm.story_services import (
    StoryServiceError,
    close_scene_room,
    create_story_area,
    grant_story_room,
    join_story_room,
    leave_story_room,
    remove_story_area,
    revoke_story_room,
    spin_up_scene_room,
    story_room_cap_check,
)
from world.instances.models import InstancedRoom


class CreateStoryAreaTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()

    def test_creates_story_area_owned_by_gm(self) -> None:
        gm = GMProfileFactory(level=GMLevel.STARTING)
        story = create_story_area(gm=gm, name="Sunken Crypt", description="Damp.")
        assert story.gm == gm
        assert story.area.origin == GridOrigin.STORY
        assert story.area.name == "Sunken Crypt"
        assert story.area.description == "Damp."

    def test_refuses_past_cap(self) -> None:
        gm = GMProfileFactory(level=GMLevel.STARTING)
        create_story_area(gm=gm, name="First")
        with self.assertRaises(StoryServiceError):
            create_story_area(gm=gm, name="Second")

    def test_promoted_area_stops_counting_against_cap(self) -> None:
        gm = GMProfileFactory(level=GMLevel.STARTING)
        story = create_story_area(gm=gm, name="First")
        story.area.origin = GridOrigin.AUTHORED
        story.area.save(update_fields=["origin"])

        # Cap freed up now that the promoted area no longer counts.
        second = create_story_area(gm=gm, name="Second")
        assert second.gm == gm

    def test_raises_when_no_cap_configured(self) -> None:
        GMLevelCap.objects.all().delete()
        gm = GMProfileFactory(level=GMLevel.STARTING)
        with self.assertRaises(StoryServiceError):
            create_story_area(gm=gm, name="First")


class RemoveStoryAreaTests(TestCase):
    def test_refuses_when_rooms_exist(self) -> None:
        story = StoryAreaFactory()
        RoomProfileFactory(area=story.area)
        with self.assertRaises(StoryServiceError):
            remove_story_area(story=story)
        assert StoryArea.objects.filter(pk=story.pk).exists()

    def test_deletes_empty_area(self) -> None:
        story = StoryAreaFactory()
        area_pk = story.area_id
        remove_story_area(story=story)
        assert not StoryArea.objects.filter(pk=story.pk).exists()
        assert not Area.objects.filter(pk=area_pk).exists()


class StoryRoomCapCheckTests(TestCase):
    def test_raises_at_cap(self) -> None:
        GMLevelCapFactory(level=GMLevel.JUNIOR, max_story_rooms_per_area=1)
        gm = GMProfileFactory(level=GMLevel.JUNIOR)
        story = StoryAreaFactory(gm=gm)
        RoomProfileFactory(area=story.area)
        with self.assertRaises(StoryServiceError):
            story_room_cap_check(gm=gm, area=story.area)

    def test_allows_under_cap(self) -> None:
        GMLevelCapFactory(level=GMLevel.JUNIOR, max_story_rooms_per_area=2)
        gm = GMProfileFactory(level=GMLevel.JUNIOR)
        story = StoryAreaFactory(gm=gm)
        RoomProfileFactory(area=story.area)
        story_room_cap_check(gm=gm, area=story.area)  # does not raise


class GrantStoryRoomTests(TestCase):
    def test_idempotent(self) -> None:
        gm = GMProfileFactory()
        room_profile = RoomProfileFactory()
        sheet = CharacterSheetFactory(character=CharacterFactory())
        grant1 = grant_story_room(gm=gm, room_profile=room_profile, sheet=sheet)
        grant2 = grant_story_room(gm=gm, room_profile=room_profile, sheet=sheet)
        assert grant1.pk == grant2.pk
        assert StoryRoomGrant.objects.filter(room=room_profile, character=sheet).count() == 1


class JoinStoryRoomTests(TestCase):
    def test_raises_without_grant(self) -> None:
        room_profile = RoomProfileFactory()
        sheet = CharacterSheetFactory(character=CharacterFactory())
        with self.assertRaises(StoryServiceError):
            join_story_room(sheet=sheet, room_profile=room_profile)

    def test_captures_return_location_and_moves(self) -> None:
        gm = GMProfileFactory()
        room_profile = RoomProfileFactory()
        origin_room = RoomProfileFactory().objectdb
        char = CharacterFactory(home=origin_room)
        sheet = CharacterSheetFactory(character=char)
        char.move_to(origin_room, quiet=True)
        StoryRoomGrantFactory(room=room_profile, character=sheet, granted_by=gm)

        destination = join_story_room(sheet=sheet, room_profile=room_profile)

        assert destination == room_profile.objectdb
        assert char.location == room_profile.objectdb
        grant = StoryRoomGrant.objects.get(room=room_profile, character=sheet)
        assert grant.return_location == origin_room


class LeaveStoryRoomTests(TestCase):
    def test_raises_without_grant(self) -> None:
        room_profile = RoomProfileFactory()
        sheet = CharacterSheetFactory(character=CharacterFactory())
        with self.assertRaises(StoryServiceError):
            leave_story_room(sheet=sheet, room_profile=room_profile)

    def test_restores_to_captured_return_location(self) -> None:
        gm = GMProfileFactory()
        room_profile = RoomProfileFactory()
        origin_room = RoomProfileFactory().objectdb
        char = CharacterFactory(home=origin_room)
        sheet = CharacterSheetFactory(character=char)
        char.move_to(origin_room, quiet=True)
        StoryRoomGrantFactory(room=room_profile, character=sheet, granted_by=gm)
        join_story_room(sheet=sheet, room_profile=room_profile)

        destination = leave_story_room(sheet=sheet, room_profile=room_profile)

        assert destination == origin_room
        assert char.location == origin_room
        grant = StoryRoomGrant.objects.get(room=room_profile, character=sheet)
        assert grant.return_location is None

    def test_falls_back_to_home_when_no_return_location(self) -> None:
        gm = GMProfileFactory()
        room_profile = RoomProfileFactory()
        home_room = RoomProfileFactory().objectdb
        char = CharacterFactory(home=home_room)
        sheet = CharacterSheetFactory(character=char)
        StoryRoomGrantFactory(
            room=room_profile,
            character=sheet,
            granted_by=gm,
            return_location=None,
        )

        destination = leave_story_room(sheet=sheet, room_profile=room_profile)

        assert destination == home_room
        assert char.location == home_room


class RevokeStoryRoomTests(TestCase):
    def test_returns_character_to_captured_origin_when_inside(self) -> None:
        gm = GMProfileFactory()
        room_profile = RoomProfileFactory()
        origin_room = RoomProfileFactory().objectdb
        home_room = RoomProfileFactory().objectdb
        char = CharacterFactory(home=home_room)
        sheet = CharacterSheetFactory(character=char)
        char.move_to(origin_room, quiet=True)
        grant = StoryRoomGrantFactory(room=room_profile, character=sheet, granted_by=gm)
        join_story_room(sheet=sheet, room_profile=room_profile)
        grant.refresh_from_db()

        revoke_story_room(grant=grant)

        assert char.location == origin_room
        assert not StoryRoomGrant.objects.filter(pk=grant.pk).exists()

    def test_deletes_without_moving_when_not_inside(self) -> None:
        grant = StoryRoomGrantFactory()
        revoke_story_room(grant=grant)
        assert not StoryRoomGrant.objects.filter(pk=grant.pk).exists()


class SpinUpSceneRoomTests(TestCase):
    def test_creates_gm_owned_instance_with_room_profile(self) -> None:
        gm = GMProfileFactory()
        instance = spin_up_scene_room(gm=gm, name="Ambush Site", description="A dark alley.")
        assert isinstance(instance, InstancedRoom)
        assert instance.gm_owner == gm
        assert instance.owner is None
        assert RoomProfile.objects.filter(objectdb=instance.room).exists()


class CloseSceneRoomTests(TestCase):
    def test_returns_joined_characters_then_completes_instance(self) -> None:
        gm = GMProfileFactory()
        instance = spin_up_scene_room(gm=gm, name="Ambush Site", description="A dark alley.")
        room_profile = RoomProfile.objects.get(objectdb=instance.room)
        room_profile_pk = room_profile.pk
        instance_pk = instance.pk

        home_room = RoomProfileFactory().objectdb
        char = CharacterFactory(home=home_room)
        sheet = CharacterSheetFactory(character=char)
        char.move_to(home_room, quiet=True)
        StoryRoomGrantFactory(room=room_profile, character=sheet, granted_by=gm)
        join_story_room(sheet=sheet, room_profile=room_profile)
        assert char.location == instance.room

        close_scene_room(instance=instance)

        # The character is returned by story_services *before*
        # complete_instanced_room runs — assert that ordering directly.
        assert char.location == home_room
        assert not StoryRoomGrant.objects.filter(room_id=room_profile_pk).exists()
        # This temp room has no Scene history, so complete_instanced_room's
        # "delete if ephemeral" path removes it (and, via the room's
        # OneToOneField CASCADE, the InstancedRoom row) — confirming
        # completion ran to the end after the character was returned.
        assert not InstancedRoom.objects.filter(pk=instance_pk).exists()
