"""AssignRoomTenantAction hands out a rung, not only a tenancy (#3902).

This action is the one player surface that mints a grant. Before the ladder it could
only make a tenant; the whole point of the issue was that a friend can give a KEY,
so the action has to be able to say which rung, and refuse the ones the actor may
not give with the service's own reason rather than a generic failure.
"""

from django.test import TestCase, tag

from actions.registry import get_action
from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.locations.constants import HolderType, LocationParentType, LocationRole
from world.locations.models import LocationOwnership, LocationTenancy
from world.scenes.factories import PersonaFactory


@tag("postgres")  # standing walks the areas_areaclosure materialized view
class AssignRoomTenantActionTests(TestCase):
    def setUp(self) -> None:
        self.profile = RoomProfileFactory()
        self.room = self.profile.objectdb
        self.friend = PersonaFactory()

    def _grant(self, character, **kwargs):
        return get_action("assign_room_tenant").run(
            actor=character, tenant_persona_id=self.friend.pk, **kwargs
        )

    def _make_owner(self, persona) -> None:
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )

    def _make_tenant(self, persona) -> None:
        LocationTenancy.objects.create(
            kind=LocationRole.TENANT,
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=persona,
        )

    def test_the_default_is_still_a_tenancy(self) -> None:
        sheet, character = character_in_room(self.profile)
        self._make_owner(sheet.primary_persona)

        result = self._grant(character)

        self.assertTrue(result.success, result.message)
        row = LocationTenancy.objects.get(tenant_persona=self.friend)
        self.assertEqual(row.kind, LocationRole.TENANT)
        self.assertEqual(row.granted_by, sheet.primary_persona)

    def test_a_tenant_gives_a_friend_a_key(self) -> None:
        sheet, character = character_in_room(self.profile)
        self._make_tenant(sheet.primary_persona)

        result = self._grant(character, kind="guest")

        self.assertTrue(result.success, result.message)
        self.assertIn("key", result.message)
        row = LocationTenancy.objects.get(tenant_persona=self.friend)
        self.assertEqual(row.kind, LocationRole.GUEST)
        self.assertEqual(row.granted_by, sheet.primary_persona)

    def test_a_tenant_is_told_why_they_cannot_install_a_tenant(self) -> None:
        sheet, character = character_in_room(self.profile)
        self._make_tenant(sheet.primary_persona)

        result = self._grant(character, kind="tenant")

        self.assertFalse(result.success)
        self.assertIn("key", result.message)
        self.assertFalse(LocationTenancy.objects.filter(tenant_persona=self.friend).exists())

    def test_only_the_owner_appoints_a_trustee(self) -> None:
        sheet, character = character_in_room(self.profile)
        self._make_owner(sheet.primary_persona)

        result = self._grant(character, kind="trustee")

        self.assertTrue(result.success, result.message)
        self.assertEqual(
            LocationTenancy.objects.get(tenant_persona=self.friend).kind, LocationRole.TRUSTEE
        )

    def test_an_unknown_rung_is_refused_before_anything_is_written(self) -> None:
        sheet, character = character_in_room(self.profile)
        self._make_owner(sheet.primary_persona)

        result = self._grant(character, kind="landlord")

        self.assertFalse(result.success)
        self.assertFalse(LocationTenancy.objects.filter(tenant_persona=self.friend).exists())
