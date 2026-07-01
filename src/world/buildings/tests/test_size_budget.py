"""Tests for the space-budget model (#670): BuildingSizeTier + construction wiring."""

from django.test import TestCase

from evennia_extensions.models import RoomSizeTier
from evennia_extensions.seeds import DEFAULT_ROOM_SIZE_NAME
from world.buildings.models import Building, BuildingKind, BuildingSizeTier
from world.buildings.seeds import ensure_building_size_tiers


class BuildingSizeTierSeedTests(TestCase):
    def test_seed_tiers_load_and_are_idempotent(self) -> None:
        ensure_building_size_tiers()
        tiers = list(BuildingSizeTier.objects.values_list("tier", "name", "space_budget"))
        self.assertEqual(len(tiers), 7)
        self.assertEqual(tiers[0], (1, "Hut", 50))
        self.assertIn((3, "House", 250), tiers)
        self.assertEqual(tiers[-1], (7, "Citadel", 5000))
        ensure_building_size_tiers()
        self.assertEqual(BuildingSizeTier.objects.count(), 7)


class BudgetFieldTests(TestCase):
    def test_max_rooms_and_rooms_per_size_tier_are_gone(self) -> None:
        building_fields = {f.name for f in Building._meta.get_fields()}
        kind_fields = {f.name for f in BuildingKind._meta.get_fields()}
        self.assertNotIn("max_rooms", building_fields)
        self.assertNotIn("rooms_per_size_tier", kind_fields)
        self.assertIn("space_budget", building_fields)
        self.assertIn("entry_room", building_fields)


class ConstructionBudgetTests(TestCase):
    """complete_building_construction snapshots budget + entry room."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import (
            CharacterFactory,
            ObjectDBFactory,
        )
        from evennia_extensions.models import RoomProfile
        from evennia_extensions.seeds import ensure_room_size_tiers
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.buildings.constants import PermitEligibility
        from world.buildings.factories import BuildingPermitDetailsFactory
        from world.buildings.seeds import ensure_building_permit_template, ensure_house_kind
        from world.buildings.services import activate_permit
        from world.character_sheets.factories import CharacterSheetFactory

        ensure_room_size_tiers()
        ensure_building_size_tiers()
        ensure_building_permit_template()
        house = ensure_house_kind()
        ward = AreaFactory(level=AreaLevel.WARD, name="budget-ward")
        ward.permit_eligibility = PermitEligibility.OPEN
        ward.save(update_fields=["permit_eligibility"])
        ward.allowed_building_kinds.add(house)

        site_area = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        site_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.update_or_create(
            objectdb=site_room, defaults={"area": site_area, "is_outdoor": True}
        )
        character = CharacterFactory()
        persona = CharacterSheetFactory(character=character).primary_persona
        permit = BuildingPermitDetailsFactory(
            item_instance__holder_character_sheet=persona.character_sheet,
            building_kind=house,
            max_target_size=10,
        )
        permit.approved_wards.add(ward)
        cls.project = activate_permit(
            permit_details=permit,
            site_room=site_room,
            acting_persona=persona,
            target_size=3,
            target_grandeur=3,
        )

    def test_construction_sets_space_budget_from_tier(self) -> None:
        from world.buildings.services import complete_building_construction

        building = complete_building_construction(self.project)
        self.assertEqual(
            building.space_budget,
            BuildingSizeTier.objects.get(tier=3).space_budget,
        )

    def test_construction_sets_entry_room_with_default_size_and_origin_coords(self) -> None:
        from world.buildings.services import complete_building_construction

        building = complete_building_construction(self.project)
        entry = building.entry_room
        self.assertIsNotNone(entry)
        self.assertEqual(entry.area, building.area)
        self.assertEqual(entry.size, RoomSizeTier.objects.get(name=DEFAULT_ROOM_SIZE_NAME))
        self.assertEqual((entry.grid_x, entry.grid_y, entry.floor), (0, 0, 0))
