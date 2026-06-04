"""Tests for the buildings models."""

from django.test import TestCase

from world.buildings.factories import (
    BuildingFactory,
    BuildingKindFactory,
    BuildingMaterialFactory,
    BuildingPermitDetailsFactory,
    MaterialLoreEffectFactory,
)


class BuildingKindModelTests(TestCase):
    def test_create(self) -> None:
        kind = BuildingKindFactory(
            name="Manor",
            rooms_per_size_tier=30,
            is_residential=True,
            is_fortified=True,
        )
        self.assertEqual(kind.name, "Manor")
        self.assertEqual(kind.rooms_per_size_tier, 30)
        self.assertTrue(kind.is_residential)
        self.assertTrue(kind.is_fortified)
        self.assertFalse(kind.is_occult)

    def test_name_unique(self) -> None:
        BuildingKindFactory(name="Cottage")
        # django_get_or_create lookups by name; same name returns existing row.
        same = BuildingKindFactory(name="Cottage")
        self.assertEqual(same.pk, BuildingKindFactory(name="Cottage").pk)


class BuildingModelTests(TestCase):
    def test_create(self) -> None:
        building = BuildingFactory(target_size=5)
        self.assertEqual(building.target_size, 5)
        # max_rooms = rooms_per_size_tier × target_size; default kind has 20×5=100.
        self.assertEqual(building.max_rooms, building.kind.rooms_per_size_tier * 5)

    def test_max_rooms_formula(self) -> None:
        manor_kind = BuildingKindFactory(name="Manor", rooms_per_size_tier=30)
        building = BuildingFactory(kind=manor_kind, target_size=8)
        self.assertEqual(building.max_rooms, 240)

    def test_computed_stats_empty_when_no_effects(self) -> None:
        building = BuildingFactory()
        BuildingMaterialFactory(building=building)
        self.assertEqual(building.computed_stats(), {})

    def test_computed_stats_aggregates_per_unit_effects(self) -> None:
        building = BuildingFactory()
        material = BuildingMaterialFactory(building=building, units=25)
        MaterialLoreEffectFactory(
            template=material.item_template,
            target_stat="resonance_amp",
            units_per_tier=5,
            magnitude_per_tier=2,
        )
        # 25 units / 5 per tier = 5 tiers; 5 × 2 magnitude = +10 resonance_amp
        self.assertEqual(building.computed_stats(), {"resonance_amp": 10})

    def test_computed_stats_respects_max_tiers(self) -> None:
        building = BuildingFactory()
        material = BuildingMaterialFactory(building=building, units=100)
        MaterialLoreEffectFactory(
            template=material.item_template,
            target_stat="prestige",
            units_per_tier=10,
            magnitude_per_tier=1,
            max_tiers=3,  # caps at 3 tiers regardless of units
        )
        # 100/10 = 10 tiers but cap=3, so 3 × 1 = 3 prestige
        self.assertEqual(building.computed_stats(), {"prestige": 3})

    def test_computed_stats_sums_multiple_effects(self) -> None:
        building = BuildingFactory()
        material = BuildingMaterialFactory(building=building, units=20)
        MaterialLoreEffectFactory(
            template=material.item_template,
            target_stat="resonance_amp",
            units_per_tier=5,
            magnitude_per_tier=1,
        )
        MaterialLoreEffectFactory(
            template=material.item_template,
            target_stat="prestige",
            units_per_tier=10,
            magnitude_per_tier=2,
        )
        # resonance_amp: 20/5 = 4 tiers × 1 = 4
        # prestige: 20/10 = 2 tiers × 2 = 4
        self.assertEqual(building.computed_stats(), {"resonance_amp": 4, "prestige": 4})


class BuildingPermitDetailsModelTests(TestCase):
    def test_create_unconsumed(self) -> None:
        permit = BuildingPermitDetailsFactory()
        self.assertIsNone(permit.consumed_at)
        self.assertIsNone(permit.consumed_by_persona)
        self.assertEqual(permit.max_target_size, 10)

    def test_holder_sheet_is_set(self) -> None:
        # #684: holder lives on item_instance.holder_character_sheet. The
        # BuildingPermitDetailsFactory's default ItemInstanceFactory leaves
        # holder unset; tests that care wire it explicitly via
        # ``item_instance__holder_character_sheet=`` like the services tests do.
        permit = BuildingPermitDetailsFactory()
        self.assertIsNotNone(permit.item_instance)
