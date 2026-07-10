"""Tests for the GM battle-staging catalog models (#2010).

BattleMapBlueprint/BlueprintBattlePlace/BlueprintFortification and
BattleUnitTemplate/BattleUnitTemplateCapability are admin-authored catalog
rows a JUNIOR-trust GM stages a live Battle from — later tasks (services,
actions, telnet, API, frontend) copy them onto Battle/BattlePlace/
Fortification/BattleUnit rows. This module only covers the catalog models
themselves.
"""

from django.db import IntegrityError
from django.test import TestCase

from world.battles.constants import BattleSideRole, FortificationKind, TerrainType, UnitQuality
from world.battles.factories import (
    BattleMapBlueprintFactory,
    BattleUnitTemplateCapabilityFactory,
    BattleUnitTemplateFactory,
    BlueprintBattlePlaceFactory,
    BlueprintFortificationFactory,
)
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import PropertyFactory


class BattleMapBlueprintTests(TestCase):
    def test_str_and_defaults(self) -> None:
        blueprint = BattleMapBlueprintFactory(name="The Sundered Vale")
        self.assertEqual(str(blueprint), "The Sundered Vale")
        self.assertTrue(blueprint.is_active)
        self.assertEqual(blueprint.description, "")


class BlueprintBattlePlaceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.blueprint = BattleMapBlueprintFactory()

    def test_unique_name_per_blueprint(self) -> None:
        BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="The Main Gates")
        with self.assertRaises(IntegrityError):
            BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="The Main Gates")

    def test_same_name_allowed_across_different_blueprints(self) -> None:
        other_blueprint = BattleMapBlueprintFactory()
        BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="The Main Gates")
        place = BlueprintBattlePlaceFactory(blueprint=other_blueprint, name="The Main Gates")
        self.assertEqual(place.name, "The Main Gates")

    def test_defaults(self) -> None:
        place = BlueprintBattlePlaceFactory(blueprint=self.blueprint)
        self.assertEqual(place.terrain_type, TerrainType.OPEN)
        self.assertEqual(place.movement_cost, 1)
        self.assertEqual(place.x, 0)
        self.assertEqual(place.y, 0)
        self.assertEqual(place.footprint_radius, 1)

    def test_str(self) -> None:
        place = BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="The Main Gates")
        self.assertEqual(str(place), f"{self.blueprint.name} / The Main Gates")


class BlueprintFortificationTests(TestCase):
    def test_defaults_and_place_relation(self) -> None:
        place = BlueprintBattlePlaceFactory()
        fort = BlueprintFortificationFactory(blueprint_place=place)
        self.assertEqual(fort.kind, FortificationKind.WALL)
        self.assertEqual(fort.max_integrity, 100)
        self.assertEqual(fort.defending_side_role, BattleSideRole.DEFENDER)
        self.assertEqual(place.fortifications.count(), 1)

    def test_multiple_fortifications_per_place(self) -> None:
        place = BlueprintBattlePlaceFactory()
        BlueprintFortificationFactory(blueprint_place=place, kind=FortificationKind.WALL)
        BlueprintFortificationFactory(blueprint_place=place, kind=FortificationKind.GATE)
        self.assertEqual(place.fortifications.count(), 2)


class BattleUnitTemplateTests(TestCase):
    def test_defaults(self) -> None:
        template = BattleUnitTemplateFactory(name="Levy Spearmen")
        self.assertEqual(str(template), "Levy Spearmen")
        self.assertEqual(template.quality, UnitQuality.TRAINED)
        self.assertEqual(template.strength, 100)
        self.assertTrue(template.is_active)
        self.assertIsNone(template.individual_count)

    def test_morale_defaults_to_default_morale_constant(self) -> None:
        from world.battles.constants import DEFAULT_MORALE

        template = BattleUnitTemplateFactory()
        self.assertEqual(template.morale, DEFAULT_MORALE)

    def test_properties_round_trip(self) -> None:
        template = BattleUnitTemplateFactory()
        prop = PropertyFactory()
        template.properties.add(prop)
        self.assertEqual(template.properties.count(), 1)
        self.assertIn(prop, template.properties.all())


class BattleUnitTemplateCapabilityTests(TestCase):
    def test_unique_per_template_capability(self) -> None:
        template = BattleUnitTemplateFactory()
        capability = CapabilityTypeFactory()
        BattleUnitTemplateCapabilityFactory(template=template, capability=capability, value=10)
        with self.assertRaises(IntegrityError):
            BattleUnitTemplateCapabilityFactory(template=template, capability=capability, value=5)

    def test_capability_values_round_trip(self) -> None:
        template = BattleUnitTemplateFactory()
        capability = CapabilityTypeFactory()
        BattleUnitTemplateCapabilityFactory(template=template, capability=capability, value=25)
        self.assertEqual(template.capabilities.count(), 1)
        self.assertEqual(template.capability_values.get(capability=capability).value, 25)
