from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationTenancy
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class LocationTenancyCreateTests(TestCase):
    def test_create_with_persona_tenant_on_room(self) -> None:
        room = RoomProfileFactory()
        persona = PersonaFactory()
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            tenant_type=HolderType.PERSONA,
            tenant_persona=persona,
        )
        self.assertEqual(row.room_profile, room)
        self.assertEqual(row.tenant_persona, persona)
        self.assertIsNone(row.ends_at)

    def test_create_with_organization_tenant_on_area(self) -> None:
        area = AreaFactory()
        org = OrganizationFactory()
        ends = timezone.now() + timedelta(days=30)
        row = LocationTenancy.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            tenant_type=HolderType.ORGANIZATION,
            tenant_organization=org,
            ends_at=ends,
        )
        self.assertEqual(row.area, area)
        self.assertEqual(row.tenant_organization, org)
        self.assertEqual(row.ends_at, ends)


class LocationTenancyDiscriminatorTests(TestCase):
    def test_clean_rejects_both_parent_fks(self) -> None:
        row = LocationTenancy(
            parent_type=LocationParentType.ROOM,
            area=AreaFactory(),
            room_profile=RoomProfileFactory(),
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_parent_fk(self) -> None:
        row = LocationTenancy(
            parent_type=LocationParentType.ROOM,
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_both_tenant_fks(self) -> None:
        row = LocationTenancy(
            parent_type=LocationParentType.ROOM,
            room_profile=RoomProfileFactory(),
            tenant_type=HolderType.PERSONA,
            tenant_persona=PersonaFactory(),
            tenant_organization=OrganizationFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_tenant_fk(self) -> None:
        row = LocationTenancy(
            parent_type=LocationParentType.ROOM,
            room_profile=RoomProfileFactory(),
            tenant_type=HolderType.PERSONA,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()


class LocationTenancyConcurrentTests(TestCase):
    def test_multiple_concurrent_tenants_per_room_allowed(self) -> None:
        room = RoomProfileFactory()
        for _ in range(2):
            LocationTenancy.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=room,
                tenant_type=HolderType.PERSONA,
                tenant_persona=PersonaFactory(),
            )
        self.assertEqual(LocationTenancy.objects.filter(room_profile=room).count(), 2)
