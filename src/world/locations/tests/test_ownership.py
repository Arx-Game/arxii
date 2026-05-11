from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class LocationOwnershipCreateTests(TestCase):
    def test_create_with_persona_holder_on_area(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        persona = PersonaFactory()
        row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=persona,
        )
        self.assertEqual(row.area, area)
        self.assertEqual(row.holder_persona, persona)
        self.assertIsNone(row.room_profile)
        self.assertIsNone(row.holder_organization)
        self.assertIsNone(row.ended_at)

    def test_create_with_organization_holder_on_room(self) -> None:
        room = RoomProfileFactory()
        org = OrganizationFactory()
        row = LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        self.assertEqual(row.room_profile, room)
        self.assertEqual(row.holder_organization, org)
        self.assertIsNone(row.area)
        self.assertIsNone(row.holder_persona)


class LocationOwnershipDiscriminatorTests(TestCase):
    def test_clean_rejects_both_parent_fks(self) -> None:
        row = LocationOwnership(
            parent_type=LocationParentType.AREA,
            area=AreaFactory(),
            room_profile=RoomProfileFactory(),
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_parent_fk(self) -> None:
        row = LocationOwnership(
            parent_type=LocationParentType.AREA,
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_both_holder_fks(self) -> None:
        row = LocationOwnership(
            parent_type=LocationParentType.AREA,
            area=AreaFactory(),
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
            holder_organization=OrganizationFactory(),
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_clean_rejects_neither_holder_fk(self) -> None:
        row = LocationOwnership(
            parent_type=LocationParentType.AREA,
            area=AreaFactory(),
            holder_type=HolderType.PERSONA,
        )
        with self.assertRaises(ValidationError):
            row.full_clean()


class LocationOwnershipUniqueActiveTests(TestCase):
    def test_cannot_have_two_active_owners_per_area(self) -> None:
        area = AreaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationOwnership.objects.create(
                parent_type=LocationParentType.AREA,
                area=area,
                holder_type=HolderType.ORGANIZATION,
                holder_organization=OrganizationFactory(),
            )

    def test_cannot_have_two_active_owners_per_room(self) -> None:
        room = RoomProfileFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room,
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            LocationOwnership.objects.create(
                parent_type=LocationParentType.ROOM,
                room_profile=room,
                holder_type=HolderType.ORGANIZATION,
                holder_organization=OrganizationFactory(),
            )

    def test_active_plus_historical_owners_allowed(self) -> None:
        area = AreaFactory()
        old = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )
        old.ended_at = timezone.now()
        old.save()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=OrganizationFactory(),
        )
        self.assertEqual(LocationOwnership.objects.filter(area=area).count(), 2)
