"""RoomEditAction (#1470) widened to owner-or-tenant standing (#2452) —
IsRoomTenantPrerequisite + set_room_display_data's own re-check both gate on
owner-OR-tenant now, not owner-only.
"""

from django.test import TestCase, tag

from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from evennia_extensions.models import ObjectDisplayData
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy


def _character_in_room(room_profile):
    sheet = CharacterSheetFactory()
    character = sheet.character
    character.location = room_profile.objectdb
    character.save()
    return sheet, character


@tag("postgres")  # is_owner/is_tenant walk the areas_areaclosure materialized view
class RoomEditActionTenantTests(TestCase):
    def setUp(self) -> None:
        self.profile = RoomProfileFactory()
        self.room = self.profile.objectdb

    def test_tenant_can_edit_name_and_description(self) -> None:
        sheet, character = _character_in_room(self.profile)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=sheet.primary_persona,
        )

        result = get_action("edit_room").run(
            actor=character, name="The Tenant's Room", description="Lived in."
        )

        self.assertTrue(result.success, result.message)
        display = ObjectDisplayData.objects.get(object=self.room)
        self.assertEqual(display.longname, "The Tenant's Room")

    def test_owner_can_still_edit(self) -> None:
        sheet, character = _character_in_room(self.profile)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            holder_type=HolderType.PERSONA,
            holder_persona=sheet.primary_persona,
        )

        result = get_action("edit_room").run(actor=character, name="Owner's Room")

        self.assertTrue(result.success, result.message)

    def test_stranger_with_no_standing_is_refused(self) -> None:
        _sheet, character = _character_in_room(self.profile)

        result = get_action("edit_room").run(actor=character, name="Hijacked")

        self.assertFalse(result.success)
        self.assertFalse(ObjectDisplayData.objects.filter(object=self.room).exists())

    def test_tenant_can_edit_via_room_id_while_standing_elsewhere(self) -> None:
        elsewhere = RoomProfileFactory()
        sheet, character = _character_in_room(elsewhere)
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=sheet.primary_persona,
        )

        result = get_action("edit_room").run(
            actor=character, room_id=self.room.pk, name="Remote Edit"
        )

        self.assertTrue(result.success, result.message)
        display = ObjectDisplayData.objects.get(object=self.room)
        self.assertEqual(display.longname, "Remote Edit")
