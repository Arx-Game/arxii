"""Crew slots (#4061 slice 3): a claimable corner under a gang, taken like a barony."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.societies.constants import CrimeTier
from world.societies.crew_slots import CrewSlotError, claim_crew_slot, open_crew_slots
from world.societies.crown import crime_tier
from world.societies.factories import OrganizationFactory
from world.societies.houses.models import FealtyEdge
from world.societies.membership_services import ensure_default_rank_ladder
from world.societies.models import CrewSlot, Turf
from world.societies.turf_services import apply_turf_push


class CrewSlotTests(TestCase):
    def setUp(self):
        self.realm_city = AreaFactory(level=AreaLevel.BARONY)
        self.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=self.realm_city)
        self.gang = OrganizationFactory(name="Ashfingers")
        ensure_default_rank_ladder(self.gang)
        apply_turf_push(self.gang, self.neighborhood, 60)
        self.corner = RoomProfileFactory(area=self.neighborhood, is_outdoor=True)
        self.alley = RoomProfileFactory(area=self.neighborhood, is_outdoor=True)
        self.slot = CrewSlot.objects.create(gang=self.gang, name="The Saltside corner")
        self.slot.rooms.add(self.corner, self.alley)

    def test_a_slot_needs_outdoor_rooms(self):
        cellar = RoomProfileFactory(area=self.neighborhood, is_outdoor=False)
        slot = CrewSlot.objects.create(gang=self.gang, name="A cellar")
        slot.rooms.add(cellar)
        with self.assertRaises(ValidationError):
            slot.full_clean()

    def test_claiming_takes_the_rooms_and_swears_to_the_gang(self):
        crew = OrganizationFactory(name="Saltside Crew")

        claim_crew_slot(self.slot, crew)

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.claimed_by, crew)
        self.assertIsNotNone(self.slot.claimed_at)
        for room in (self.corner, self.alley):
            self.assertEqual(Turf.objects.get(room_profile=room).controlling_org, crew)
        self.assertEqual(FealtyEdge.objects.get(vassal=crew).liege, self.gang)
        self.assertEqual(crime_tier(crew), CrimeTier.CREW)
        self.assertNotIn(self.slot, open_crew_slots())

    def test_a_claimed_or_inactive_slot_cannot_be_taken(self):
        claim_crew_slot(self.slot, OrganizationFactory(name="First"))
        with self.assertRaises(CrewSlotError):
            claim_crew_slot(self.slot, OrganizationFactory(name="Second"))
        dormant = CrewSlot.objects.create(gang=self.gang, name="Dormant", is_active=False)
        dormant.rooms.add(RoomProfileFactory(area=self.neighborhood, is_outdoor=True))
        with self.assertRaises(CrewSlotError):
            claim_crew_slot(dormant, OrganizationFactory(name="Third"))
        self.assertEqual([s.pk for s in open_crew_slots()], [])
