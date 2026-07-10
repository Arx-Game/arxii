"""Tenancy player seam + primary home (#670): assign / end / set_primary_home."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import (
    RoomEditError,
    assign_room_tenant,
    end_room_tenancy,
    end_tenancy,
    set_primary_home,
)
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


def _pc_persona():
    character = CharacterFactory()
    return CharacterSheetFactory(character=character).primary_persona


class TenancyServiceBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.area = AreaFactory(level=AreaLevel.BUILDING)
        cls.room = RoomProfileFactory(area=cls.area)
        cls.owner = _pc_persona()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=cls.area,
            holder_type=HolderType.PERSONA,
            holder_persona=cls.owner,
        )
        cls.tenant = _pc_persona()
        cls.stranger = _pc_persona()


class AssignRoomTenantTests(TenancyServiceBase):
    def test_owner_assigns_room_tenant(self) -> None:
        tenancy = assign_room_tenant(
            persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant
        )
        self.assertEqual(tenancy.room_profile, self.room)
        self.assertEqual(tenancy.tenant_persona, self.tenant)
        self.assertIsNone(tenancy.ends_at)

    def test_non_owner_cannot_assign(self) -> None:
        with self.assertRaises(RoomEditError):
            assign_room_tenant(
                persona=self.stranger, room=self.room.objectdb, tenant_persona=self.tenant
            )


class EndRoomTenancyTests(TenancyServiceBase):
    def test_owner_or_tenant_ends_tenancy(self) -> None:
        tenancy = assign_room_tenant(
            persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant
        )
        ended = end_room_tenancy(persona=self.tenant, tenancy=tenancy)
        self.assertIsNotNone(ended.ends_at)

        tenancy2 = assign_room_tenant(
            persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant
        )
        ended2 = end_room_tenancy(persona=self.owner, tenancy=tenancy2)
        self.assertIsNotNone(ended2.ends_at)

    def test_stranger_cannot_end(self) -> None:
        tenancy = assign_room_tenant(
            persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant
        )
        with self.assertRaises(RoomEditError):
            end_room_tenancy(persona=self.stranger, tenancy=tenancy)


class SetPrimaryHomeTests(TenancyServiceBase):
    def test_set_primary_home_requires_active_tenancy(self) -> None:
        with self.assertRaises(RoomEditError):
            set_primary_home(persona=self.tenant, room=self.room.objectdb)

    def test_set_primary_home_flags_tenancy_and_syncs_residence(self) -> None:
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        tenancy = set_primary_home(persona=self.tenant, room=self.room.objectdb)
        self.assertTrue(tenancy.is_primary_home)
        character = self.tenant.character_sheet.character
        self.assertEqual(character.home, self.room.objectdb)

    def test_switching_home_moves_the_flag(self) -> None:
        other_room = RoomProfileFactory(area=self.area)
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        assign_room_tenant(persona=self.owner, room=other_room.objectdb, tenant_persona=self.tenant)
        set_primary_home(persona=self.tenant, room=self.room.objectdb)
        set_primary_home(persona=self.tenant, room=other_room.objectdb)
        flags = LocationTenancy.objects.filter(tenant_persona=self.tenant, is_primary_home=True)
        self.assertEqual(flags.count(), 1)
        self.assertEqual(flags.get().room_profile, other_room)

    def test_writes_current_residence(self) -> None:
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        set_primary_home(persona=self.tenant, room=self.room.objectdb)
        self.tenant.character_sheet.refresh_from_db()
        self.assertEqual(self.tenant.character_sheet.current_residence, self.room)

    def test_redeclare_moves_current_residence_and_clears_old_primary_flag(self) -> None:
        """Journey 4: declare A then B → only B is current_residence; A's flag clears."""
        other_room = RoomProfileFactory(area=self.area)
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        assign_room_tenant(persona=self.owner, room=other_room.objectdb, tenant_persona=self.tenant)
        set_primary_home(persona=self.tenant, room=self.room.objectdb)
        set_primary_home(persona=self.tenant, room=other_room.objectdb)

        self.tenant.character_sheet.refresh_from_db()
        self.assertEqual(self.tenant.character_sheet.current_residence, other_room)
        # Query fresh (not the stale in-memory instance) — is_primary_home is flipped via a
        # bulk .update(), which bypasses the SharedMemoryModel identity-map cache.
        flags = LocationTenancy.objects.filter(tenant_persona=self.tenant, is_primary_home=True)
        self.assertEqual(flags.count(), 1)
        self.assertEqual(flags.get().room_profile, other_room)


class SetPrimaryHomeOrgStandingTests(TenancyServiceBase):
    """Journey 2 (#2036): org-derived standing (no direct persona row) mints a personal one."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org = OrganizationFactory()
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.room,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=cls.org,
        )
        cls.member = _pc_persona()
        OrganizationMembershipFactory(organization=cls.org, persona=cls.member)

    def test_org_member_with_no_direct_row_can_claim_via_set_primary_home(self) -> None:
        self.assertFalse(
            LocationTenancy.objects.filter(
                tenant_persona=self.member, room_profile=self.room
            ).exists()
        )
        tenancy = set_primary_home(persona=self.member, room=self.room.objectdb)

        self.assertEqual(tenancy.tenant_persona, self.member)
        self.assertEqual(tenancy.room_profile, self.room)
        self.assertTrue(tenancy.is_primary_home)
        self.member.character_sheet.refresh_from_db()
        self.assertEqual(self.member.character_sheet.current_residence, self.room)

    def test_org_row_itself_is_not_flagged_primary(self) -> None:
        set_primary_home(persona=self.member, room=self.room.objectdb)
        org_row = LocationTenancy.objects.get(tenant_organization=self.org)
        self.assertFalse(org_row.is_primary_home)

    def test_second_org_member_claims_independently(self) -> None:
        second_member = _pc_persona()
        OrganizationMembershipFactory(organization=self.org, persona=second_member)

        first_tenancy = set_primary_home(persona=self.member, room=self.room.objectdb)
        second_tenancy = set_primary_home(persona=second_member, room=self.room.objectdb)

        self.assertNotEqual(first_tenancy.pk, second_tenancy.pk)
        first_tenancy.refresh_from_db()
        self.assertTrue(first_tenancy.is_primary_home)
        self.assertTrue(second_tenancy.is_primary_home)
        self.member.character_sheet.refresh_from_db()
        second_member.character_sheet.refresh_from_db()
        self.assertEqual(self.member.character_sheet.current_residence, self.room)
        self.assertEqual(second_member.character_sheet.current_residence, self.room)

    def test_stranger_with_no_standing_still_rejected(self) -> None:
        with self.assertRaises(RoomEditError):
            set_primary_home(persona=self.stranger, room=self.room.objectdb)


class EndTenancyClearsResidenceTests(TenancyServiceBase):
    """Journey 6 (#2036): ending the declared-residence tenancy clears current_residence."""

    def test_ending_the_residence_tenancy_clears_current_residence(self) -> None:
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        tenancy = set_primary_home(persona=self.tenant, room=self.room.objectdb)
        self.tenant.character_sheet.refresh_from_db()
        self.assertEqual(self.tenant.character_sheet.current_residence, self.room)

        end_tenancy(tenancy)

        self.tenant.character_sheet.refresh_from_db()
        self.assertIsNone(self.tenant.character_sheet.current_residence)

    def test_ending_a_different_tenancy_leaves_residence_untouched(self) -> None:
        other_room = RoomProfileFactory(area=self.area)
        assign_room_tenant(persona=self.owner, room=self.room.objectdb, tenant_persona=self.tenant)
        other_tenancy = assign_room_tenant(
            persona=self.owner, room=other_room.objectdb, tenant_persona=self.tenant
        )
        set_primary_home(persona=self.tenant, room=self.room.objectdb)

        end_tenancy(other_tenancy)

        self.tenant.character_sheet.refresh_from_db()
        self.assertEqual(self.tenant.character_sheet.current_residence, self.room)
