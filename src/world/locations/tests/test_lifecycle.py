from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import (
    _validate_holder_kwargs,
    _validate_location_kwargs,
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
