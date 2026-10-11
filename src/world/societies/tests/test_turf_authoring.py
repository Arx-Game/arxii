"""Tests for the #4239 crime-ladder authoring services: claim a ward, add a
gang beneath a family, open a crew slot."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.societies.crew_slots import CrewSlotError, open_crew_slot
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.models import FealtyEdge
from world.societies.models import Turf
from world.societies.turf_services import (
    GRIP_MAX,
    TurfAuthoringError,
    add_gang,
    claim_ward,
)


class TurfAuthoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        OrganizationTypeFactory(name="gang")
        cls.city = AreaFactory(level=AreaLevel.BARONY)
        cls.ward = AreaFactory(level=AreaLevel.WARD, parent=cls.city)
        cls.neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=cls.ward)
        cls.elsewhere = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=cls.city)
        cls.family = OrganizationFactory(name="the Saltside family")

    def test_claim_ward_holds_at_full_grip(self):
        turf = claim_ward(organization=self.family, area=self.ward)
        self.assertEqual(turf.controlling_org, self.family)
        self.assertEqual(turf.grip, GRIP_MAX)
        self.assertIsNotNone(turf.income_stream)

    def test_claim_ward_refuses_a_neighborhood_and_rival_ground(self):
        with self.assertRaises(TurfAuthoringError):
            claim_ward(organization=self.family, area=self.neighborhood)
        rival = OrganizationFactory(name="the Wharf family")
        claim_ward(organization=rival, area=self.ward)
        with self.assertRaises(TurfAuthoringError):
            claim_ward(organization=self.family, area=self.ward)
        claim_ward(organization=rival, area=self.ward)

    def test_add_gang_makes_the_org_the_oath_and_the_ground(self):
        claim_ward(organization=self.family, area=self.ward)
        gang = add_gang(family_org=self.family, name="Ashfingers", neighborhood=self.neighborhood)
        self.assertEqual(gang.parent_org, self.family)
        self.assertEqual(gang.org_type.name, "gang")
        self.assertTrue(gang.ranks.exists())
        self.assertTrue(FealtyEdge.objects.filter(vassal=gang, liege=self.family).exists())
        turf = Turf.objects.get(area=self.neighborhood)
        self.assertEqual(turf.controlling_org, gang)

    def test_add_gang_refuses_outside_the_family_ward_and_bad_input(self):
        claim_ward(organization=self.family, area=self.ward)
        with self.assertRaises(TurfAuthoringError):
            add_gang(family_org=self.family, name="Strays", neighborhood=self.elsewhere)
        with self.assertRaises(TurfAuthoringError):
            add_gang(family_org=self.family, name="  ", neighborhood=self.neighborhood)
        with self.assertRaises(TurfAuthoringError):
            add_gang(family_org=self.family, name="Wardens", neighborhood=self.ward)

    def test_add_gang_without_a_ward_takes_any_neighborhood(self):
        gang = add_gang(family_org=self.family, name="Strays", neighborhood=self.elsewhere)
        self.assertEqual(Turf.objects.get(area=self.elsewhere).controlling_org, gang)

    def test_open_crew_slot(self):
        gang = add_gang(family_org=self.family, name="Ashfingers", neighborhood=self.neighborhood)
        corner = RoomProfileFactory(area=self.neighborhood, is_outdoor=True)
        alley = RoomProfileFactory(area=self.neighborhood, is_outdoor=True)
        slot = open_crew_slot(gang=gang, name="The Saltside corner", rooms=[corner, alley])
        self.assertTrue(slot.is_open)
        self.assertEqual(set(slot.rooms.all()), {corner, alley})
        cellar = RoomProfileFactory(area=self.neighborhood, is_outdoor=False)
        with self.assertRaises(CrewSlotError):
            open_crew_slot(gang=gang, name="Cellar", rooms=[cellar])
        with self.assertRaises(CrewSlotError):
            open_crew_slot(gang=gang, name="Nowhere", rooms=[])
