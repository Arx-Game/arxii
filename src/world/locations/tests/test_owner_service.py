from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import effective_owner
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class EffectiveOwnerCascadeTests(TestCase):
    def setUp(self) -> None:
        self.region = AreaFactory(level=AreaLevel.REGION)
        self.city = AreaFactory(level=AreaLevel.CITY, parent=self.region)
        self.ward = AreaFactory(level=AreaLevel.WARD, parent=self.city)
        self.profile = RoomProfileFactory(area=self.ward)
        self.room = self.profile.objectdb

    def test_returns_none_when_no_ownership_in_chain(self) -> None:
        self.assertIsNone(effective_owner(self.room))

    def test_room_owner_beats_area_owner(self) -> None:
        ward_persona = PersonaFactory()
        room_persona = PersonaFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=ward_persona,
        )
        room_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            holder_type=HolderType.PERSONA,
            holder_persona=room_persona,
        )
        result = effective_owner(self.room)
        self.assertEqual(result, room_row)

    def test_more_specific_area_owner_wins(self) -> None:
        org_city = OrganizationFactory()
        org_ward = OrganizationFactory()
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org_city,
        )
        ward_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org_ward,
        )
        result = effective_owner(self.room)
        self.assertEqual(result, ward_row)

    def test_area_owner_cascades_to_room(self) -> None:
        org = OrganizationFactory()
        city_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.city,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=org,
        )
        result = effective_owner(self.room)
        self.assertEqual(result, city_row)

    def test_historical_owner_ignored(self) -> None:
        old_persona = PersonaFactory()
        old_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=self.ward,
            holder_type=HolderType.PERSONA,
            holder_persona=old_persona,
        )
        old_row.ended_at = timezone.now()
        old_row.save()
        self.assertIsNone(effective_owner(self.room))


class EffectiveOwnerEdgeCaseTests(TestCase):
    def test_room_with_no_profile_returns_none(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        profile.delete()
        room.refresh_from_db()
        self.assertIsNone(effective_owner(room))

    def test_room_with_profile_but_no_area_returns_none(self) -> None:
        profile = RoomProfileFactory()  # area defaults to None
        self.assertIsNone(effective_owner(profile.objectdb))
