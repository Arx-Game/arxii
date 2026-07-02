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
    set_primary_home,
)


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
