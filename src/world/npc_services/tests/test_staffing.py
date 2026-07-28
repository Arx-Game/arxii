"""Venue auto-staffing tests (#2827 phase 1)."""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import RoomProfileFactory
from world.buildings.factories import BuildingFactory, BuildingKindFactory
from world.npc_services.factories import (
    NPCRoleFactory,
    StaffingProfileFactory,
    StaffingProfileLineFactory,
)
from world.npc_services.models import Functionary
from world.npc_services.staffing import ensure_staffing_for_building, refill_staffing_sweep
from world.scenes.factories import PersonaFactory


class StaffingTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.kind = BuildingKindFactory(name="Inn")
        cls.profile = StaffingProfileFactory(building_kind=cls.kind)
        cls.innkeeper = NPCRoleFactory(name="Innkeeper")
        cls.barmaid = NPCRoleFactory(name="Barmaid")
        StaffingProfileLineFactory(profile=cls.profile, role=cls.innkeeper)
        StaffingProfileLineFactory(profile=cls.profile, role=cls.barmaid)

    def _building(self):
        room = RoomProfileFactory()
        return BuildingFactory(kind=self.kind, entry_room=room)


class EnsureStaffingTests(StaffingTestBase):
    def test_activation_staffs_the_entry_room(self):
        building = self._building()
        created = ensure_staffing_for_building(building)
        self.assertEqual(created, 2)
        placed_roles = set(
            Functionary.objects.filter(room=building.entry_room, is_active=True).values_list(
                "role__name", flat=True
            )
        )
        self.assertEqual(placed_roles, {"Innkeeper", "Barmaid"})

    def test_idempotent_on_active_slots(self):
        building = self._building()
        ensure_staffing_for_building(building)
        self.assertEqual(ensure_staffing_for_building(building), 0)

    def test_no_profile_or_room_is_noop(self):
        unprofiled = BuildingFactory(kind=BuildingKindFactory(name="Warehouse"))
        self.assertEqual(ensure_staffing_for_building(unprofiled), 0)

    def test_vacated_slot_refills_as_fresh_faceless_hire(self):
        building = self._building()
        ensure_staffing_for_building(building)
        slot = Functionary.objects.get(room=building.entry_room, role=self.barmaid)
        # A materialized worker was extracted: named, persona-linked, inactive.
        slot.name_override = "Sella"
        slot.persona = PersonaFactory()
        slot.is_active = False
        slot.save()

        self.assertEqual(ensure_staffing_for_building(building), 1)
        slot.refresh_from_db()
        self.assertTrue(slot.is_active)
        self.assertEqual(slot.name_override, "")
        self.assertIsNone(slot.persona)


class RefillSweepTests(StaffingTestBase):
    def test_sweep_covers_activated_buildings_only(self):
        activated = self._building()
        activated.property_activated_at = timezone.now()
        activated.save(update_fields=["property_activated_at"])
        self._building()  # never activated — sweep must skip it
        self.assertEqual(refill_staffing_sweep(), 2)
        self.assertEqual(refill_staffing_sweep(), 0)
