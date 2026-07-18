"""IsRoomTenantPrerequisite must anchor on the room_id kwarg when supplied
(mirroring IsRoomOwnerPrerequisite), not always the actor's current location —
required so RoomEditAction (which supports web-canvas room_id targeting) can
use this prerequisite (#2452).
"""

from django.test import TestCase, tag

from actions.prerequisites import IsRoomTenantPrerequisite
from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy


@tag("postgres")  # is_owner/is_tenant walk the areas_areaclosure materialized view
class RoomIdAnchoringTests(TestCase):
    def setUp(self) -> None:
        self.target_profile = RoomProfileFactory()
        self.elsewhere_profile = RoomProfileFactory()

    def test_room_id_kwarg_checks_the_targeted_room_not_actors_location(self) -> None:
        sheet, character = character_in_room(self.elsewhere_profile)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.target_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=sheet.primary_persona,
        )
        context = {"kwargs": {"room_id": self.target_profile.objectdb_id}}

        met, _msg = IsRoomTenantPrerequisite().is_met(character, context=context)

        assert met is True

    def test_room_id_kwarg_refuses_standing_only_in_actors_own_location(self) -> None:
        sheet, character = character_in_room(self.elsewhere_profile)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.elsewhere_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=sheet.primary_persona,
        )
        context = {"kwargs": {"room_id": self.target_profile.objectdb_id}}

        met, msg = IsRoomTenantPrerequisite().is_met(character, context=context)

        assert met is False
        assert "no standing" in msg.lower()

    def test_tenant_standing_via_room_id(self) -> None:
        sheet, character = character_in_room(self.elsewhere_profile)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.target_profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=sheet.primary_persona,
        )
        context = {"kwargs": {"room_id": self.target_profile.objectdb_id}}

        met, _msg = IsRoomTenantPrerequisite().is_met(character, context=context)

        assert met is True

    def test_no_room_id_falls_back_to_actors_location(self) -> None:
        sheet, character = character_in_room(self.target_profile)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.target_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=sheet.primary_persona,
        )

        met, _msg = IsRoomTenantPrerequisite().is_met(character, context=None)

        assert met is True

    def test_unknown_room_id_is_refused(self) -> None:
        _sheet, character = character_in_room(self.elsewhere_profile)
        context = {"kwargs": {"room_id": 999999999}}

        met, msg = IsRoomTenantPrerequisite().is_met(character, context=context)

        assert met is False
        assert msg == "No such room."
