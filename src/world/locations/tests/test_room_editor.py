"""Room-editor MVP (#1470) — owner-gated name/description/public-private edits.

Covers the ``set_room_display_data`` service (writes + owner gate + the
public-toggle scene-privacy guard) and the ``IsRoomOwnerPrerequisite`` gate.
"""

from django.test import TestCase

from actions.prerequisites import IsRoomOwnerPrerequisite
from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import ObjectDisplayData, RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import RoomEditError, set_room_display_data
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import PersonaFactory, SceneFactory


def _own_room(profile, persona) -> LocationOwnership:
    return LocationOwnership.objects.create(
        parent_type=LocationParentType.ROOM,
        room_profile=profile,
        holder_type=HolderType.PERSONA,
        holder_persona=persona,
    )


class SetRoomDisplayDataTests(TestCase):
    def setUp(self) -> None:
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=self.ward)
        self.room = self.profile.objectdb
        self.owner = PersonaFactory()
        _own_room(self.profile, self.owner)

    def test_owner_sets_name_description_and_privacy(self) -> None:
        set_room_display_data(
            room=self.room,
            persona=self.owner,
            name="The Great Hall",
            description="Lofty and lamplit.",
            is_public=False,
        )
        display = ObjectDisplayData.objects.get(object=self.room)
        assert display.longname == "The Great Hall"
        assert display.permanent_description == "Lofty and lamplit."
        assert RoomProfile.objects.get(objectdb=self.room).is_public is False

    def test_only_supplied_fields_change(self) -> None:
        ObjectDisplayData.objects.create(
            object=self.room, longname="Old", permanent_description="Old desc."
        )
        set_room_display_data(room=self.room, persona=self.owner, name="New")
        display = ObjectDisplayData.objects.get(object=self.room)
        assert display.longname == "New"
        assert display.permanent_description == "Old desc."

    def test_non_owner_is_refused(self) -> None:
        stranger = PersonaFactory()
        with self.assertRaises(RoomEditError):
            set_room_display_data(room=self.room, persona=stranger, name="Hijacked")
        assert not ObjectDisplayData.objects.filter(object=self.room).exists()

    def test_cannot_make_public_while_a_non_public_scene_is_active(self) -> None:
        self.profile.is_public = False
        self.profile.save(update_fields=["is_public"])
        SceneFactory(location=self.room, privacy_mode=ScenePrivacyMode.PRIVATE, is_active=True)
        with self.assertRaises(RoomEditError):
            set_room_display_data(room=self.room, persona=self.owner, is_public=True)
        assert RoomProfile.objects.get(objectdb=self.room).is_public is False

    def test_can_make_public_with_no_active_private_scene(self) -> None:
        self.profile.is_public = False
        self.profile.save(update_fields=["is_public"])
        set_room_display_data(room=self.room, persona=self.owner, is_public=True)
        assert RoomProfile.objects.get(objectdb=self.room).is_public is True

    def test_bypass_ownership_edits_room_the_persona_does_not_own(self) -> None:
        stranger = PersonaFactory()
        set_room_display_data(
            room=self.room,
            persona=stranger,
            name="Staff Edit",
            bypass_ownership=True,
        )
        display = ObjectDisplayData.objects.get(object=self.room)
        assert display.longname == "Staff Edit"

    def test_bypass_ownership_still_refuses_public_during_active_non_public_scene(
        self,
    ) -> None:
        stranger = PersonaFactory()
        self.profile.is_public = False
        self.profile.save(update_fields=["is_public"])
        SceneFactory(location=self.room, privacy_mode=ScenePrivacyMode.PRIVATE, is_active=True)
        with self.assertRaises(RoomEditError):
            set_room_display_data(
                room=self.room,
                persona=stranger,
                is_public=True,
                bypass_ownership=True,
            )
        assert RoomProfile.objects.get(objectdb=self.room).is_public is False


class IsRoomOwnerPrerequisiteTests(TestCase):
    def setUp(self) -> None:
        self.ward = AreaFactory(level=AreaLevel.WARD)
        self.profile = RoomProfileFactory(area=self.ward)
        self.room = self.profile.objectdb

    def test_owner_standing_in_their_room_is_met(self) -> None:
        sheet = CharacterSheetFactory()
        _own_room(self.profile, sheet.primary_persona)
        character = sheet.character
        character.location = self.room
        met, _msg = IsRoomOwnerPrerequisite().is_met(character)
        assert met is True

    def test_non_owner_is_refused(self) -> None:
        sheet = CharacterSheetFactory()
        character = sheet.character
        character.location = self.room
        met, msg = IsRoomOwnerPrerequisite().is_met(character)
        assert met is False
        assert "own" in msg.lower()
