from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership, LocationTenancy
from world.locations.services import (
    _validate_holder_kwargs,
    _validate_location_kwargs,
    end_tenancy,
    grant_tenancy,
    transfer_ownership,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class ValidateLocationKwargsTests(TestCase):
    def test_accepts_area_only(self) -> None:
        _validate_location_kwargs(AreaFactory(), None)

    def test_accepts_room_profile_only(self) -> None:
        _validate_location_kwargs(None, RoomProfileFactory())

    def test_rejects_both_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_location_kwargs(AreaFactory(), RoomProfileFactory())

    def test_rejects_neither_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_location_kwargs(None, None)


class ValidateHolderKwargsTests(TestCase):
    def test_accepts_persona_only(self) -> None:
        _validate_holder_kwargs(PersonaFactory(), None)

    def test_accepts_organization_only(self) -> None:
        _validate_holder_kwargs(None, OrganizationFactory())

    def test_rejects_both_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_holder_kwargs(PersonaFactory(), OrganizationFactory())

    def test_rejects_neither_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_holder_kwargs(None, None)


class TransferOwnershipClaimTests(TestCase):
    def test_creates_active_row_when_no_existing_owner(self) -> None:
        area = AreaFactory()
        persona = PersonaFactory()
        row = transfer_ownership(area=area, to_persona=persona)
        self.assertIsNone(row.ended_at)
        self.assertEqual(row.area, area)
        self.assertEqual(row.holder_persona, persona)
        self.assertEqual(row.parent_type, LocationParentType.AREA)
        self.assertEqual(row.holder_type, HolderType.PERSONA)

    def test_org_holder_on_room(self) -> None:
        room = RoomProfileFactory()
        org = OrganizationFactory()
        row = transfer_ownership(room_profile=room, to_organization=org)
        self.assertEqual(row.room_profile, room)
        self.assertEqual(row.holder_organization, org)
        self.assertEqual(row.parent_type, LocationParentType.ROOM)
        self.assertEqual(row.holder_type, HolderType.ORGANIZATION)


class TransferOwnershipExistingOwnerTests(TestCase):
    def test_ends_existing_and_creates_new(self) -> None:
        area = AreaFactory()
        old_persona = PersonaFactory()
        new_persona = PersonaFactory()
        old = transfer_ownership(area=area, to_persona=old_persona)
        new = transfer_ownership(area=area, to_persona=new_persona)
        old.refresh_from_db()
        self.assertIsNotNone(old.ended_at)
        self.assertIsNone(new.ended_at)
        self.assertEqual(
            LocationOwnership.objects.filter(area=area, ended_at__isnull=True).count(),
            1,
        )
        self.assertEqual(LocationOwnership.objects.filter(area=area).count(), 2)

    def test_old_ended_at_matches_new_acquired_at(self) -> None:
        area = AreaFactory()
        transfer_ownership(area=area, to_persona=PersonaFactory())
        new = transfer_ownership(area=area, to_persona=PersonaFactory())
        old = LocationOwnership.objects.get(area=area, ended_at__isnull=False)
        self.assertEqual(old.ended_at, new.acquired_at)

    def test_caller_supplied_transferred_at_honored(self) -> None:
        area = AreaFactory()
        explicit_when = timezone.now() - timedelta(days=5)
        transfer_ownership(area=area, to_persona=PersonaFactory())
        transfer_ownership(area=area, to_persona=PersonaFactory(), transferred_at=explicit_when)
        old = LocationOwnership.objects.get(area=area, ended_at__isnull=False)
        new = LocationOwnership.objects.get(area=area, ended_at__isnull=True)
        self.assertEqual(old.ended_at, explicit_when)
        self.assertEqual(new.acquired_at, explicit_when)


class TransferOwnershipValidationTests(TestCase):
    def test_missing_parent_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer_ownership(to_persona=PersonaFactory())

    def test_both_parents_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer_ownership(
                area=AreaFactory(),
                room_profile=RoomProfileFactory(),
                to_persona=PersonaFactory(),
            )

    def test_missing_holder_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer_ownership(area=AreaFactory())

    def test_both_holders_raises(self) -> None:
        with self.assertRaises(ValueError):
            transfer_ownership(
                area=AreaFactory(),
                to_persona=PersonaFactory(),
                to_organization=OrganizationFactory(),
            )


class GrantTenancyTests(TestCase):
    def test_persona_tenant_on_room(self) -> None:
        room = RoomProfileFactory()
        persona = PersonaFactory()
        row = grant_tenancy(room_profile=room, tenant_persona=persona)
        self.assertEqual(row.room_profile, room)
        self.assertEqual(row.tenant_persona, persona)
        self.assertEqual(row.parent_type, LocationParentType.ROOM)
        self.assertEqual(row.tenant_type, HolderType.PERSONA)
        self.assertIsNone(row.ends_at)

    def test_organization_tenant_on_area(self) -> None:
        area = AreaFactory()
        org = OrganizationFactory()
        row = grant_tenancy(area=area, tenant_organization=org)
        self.assertEqual(row.area, area)
        self.assertEqual(row.tenant_organization, org)
        self.assertEqual(row.parent_type, LocationParentType.AREA)
        self.assertEqual(row.tenant_type, HolderType.ORGANIZATION)

    def test_with_planned_ends_at(self) -> None:
        room = RoomProfileFactory()
        expiry = timezone.now() + timedelta(days=30)
        row = grant_tenancy(room_profile=room, tenant_persona=PersonaFactory(), ends_at=expiry)
        self.assertEqual(row.ends_at, expiry)

    def test_multiple_concurrent_tenancies_allowed(self) -> None:
        room = RoomProfileFactory()
        for _ in range(3):
            grant_tenancy(room_profile=room, tenant_persona=PersonaFactory())
        self.assertEqual(LocationTenancy.objects.filter(room_profile=room).count(), 3)


class GrantTenancyValidationTests(TestCase):
    def test_missing_parent_raises(self) -> None:
        with self.assertRaises(ValueError):
            grant_tenancy(tenant_persona=PersonaFactory())

    def test_both_parents_raises(self) -> None:
        with self.assertRaises(ValueError):
            grant_tenancy(
                area=AreaFactory(),
                room_profile=RoomProfileFactory(),
                tenant_persona=PersonaFactory(),
            )

    def test_missing_tenant_raises(self) -> None:
        with self.assertRaises(ValueError):
            grant_tenancy(room_profile=RoomProfileFactory())

    def test_both_tenants_raises(self) -> None:
        with self.assertRaises(ValueError):
            grant_tenancy(
                room_profile=RoomProfileFactory(),
                tenant_persona=PersonaFactory(),
                tenant_organization=OrganizationFactory(),
            )


class EndTenancyTests(TestCase):
    def test_defaults_to_now(self) -> None:
        tenancy = grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=PersonaFactory())
        before = timezone.now()
        result = end_tenancy(tenancy)
        after = timezone.now()
        self.assertIsNotNone(result.ends_at)
        self.assertGreaterEqual(result.ends_at, before)
        self.assertLessEqual(result.ends_at, after)

    def test_honors_supplied_ended_at(self) -> None:
        tenancy = grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=PersonaFactory())
        explicit = timezone.now() - timedelta(hours=2)
        result = end_tenancy(tenancy, ended_at=explicit)
        self.assertEqual(result.ends_at, explicit)

    def test_returns_same_instance(self) -> None:
        tenancy = grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=PersonaFactory())
        result = end_tenancy(tenancy)
        self.assertIs(result, tenancy)

    def test_idempotent_re_end_overwrites(self) -> None:
        tenancy = grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=PersonaFactory())
        first = timezone.now() - timedelta(days=2)
        second = timezone.now() - timedelta(days=1)
        end_tenancy(tenancy, ended_at=first)
        tenancy.refresh_from_db()
        self.assertEqual(tenancy.ends_at, first)
        end_tenancy(tenancy, ended_at=second)
        tenancy.refresh_from_db()
        self.assertEqual(tenancy.ends_at, second)
