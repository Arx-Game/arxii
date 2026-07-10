from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.battles.constants import (
    BattleActionScope,
    BattleOutcome,
    BattleSideRole,
    BattleUnitStatus,
    FortificationKind,
    TerrainType,
    UnitQuality,
    VehicleKind,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
    BattleVehicleFactory,
    FortificationFactory,
)
from world.battles.models import (
    BattleUnit,
    BattleUnitCapability,
    TechniquePropertyAffinity,
    TerrainPropertyEffect,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
from world.magic.factories import TechniqueFactory
from world.mechanics.factories import PropertyFactory


class BattleModelTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Siege of Test Keep")

    def test_battle_auto_creates_scene(self) -> None:
        self.assertIsNotNone(self.battle.scene_id)
        self.assertEqual(self.battle.scene.name, "Siege of Test Keep")
        self.assertFalse(self.battle.is_concluded)

    def test_battle_afk_peril_override_defaults_false(self) -> None:
        from world.battles.factories import BattleFactory

        battle = BattleFactory()
        assert battle.afk_peril_override is False

    def test_sides_and_units(self) -> None:
        defender = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        place = BattlePlaceFactory(battle=self.battle, name="The Main Gates")
        unit = BattleUnitFactory(
            battle=self.battle,
            side=defender,
            place=place,
            descriptor="zombies-on-nightmares",
            strength=80,
        )
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)
        self.assertEqual(self.battle.sides.count(), 1)
        self.assertEqual(defender.units.count(), 1)
        self.assertEqual(self.battle.outcome, BattleOutcome.UNRESOLVED)

    def test_unit_factory_side_matches_battle(self) -> None:
        unit = BattleUnitFactory()
        self.assertEqual(unit.battle_id, unit.side.battle_id)

    def test_battle_side_covenant_defaults_to_none(self) -> None:
        side = BattleSideFactory()
        self.assertIsNone(side.covenant)

    def test_battle_side_covenant_can_be_set(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        side = BattleSideFactory(covenant=covenant)
        self.assertEqual(side.covenant_id, covenant.pk)


class BattleActionDeclarationTechniqueTests(TestCase):
    def test_declaration_requires_technique(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        technique = TechniqueFactory()
        declaration = BattleActionDeclarationFactory(technique=technique)
        self.assertEqual(declaration.technique, technique)

    def test_declaration_scope_defaults_to_unit(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        decl = BattleActionDeclarationFactory()
        self.assertEqual(decl.scope, BattleActionScope.UNIT)
        self.assertIsNone(decl.target_place)
        self.assertIsNone(decl.target_side)

    def test_declaration_scope_side_accepts_target_side(self) -> None:
        from world.battles.factories import BattleActionDeclarationFactory

        battle = BattleFactory()
        # DEFENDER avoids colliding with the participant subfactory's default
        # ATTACKER-role BattleSide on the same battle (unique_battle_side_role).
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        decl = BattleActionDeclarationFactory(
            battle_round__battle=battle,
            scope=BattleActionScope.SIDE,
            target_side=side,
        )
        self.assertEqual(decl.target_side_id, side.pk)


class BattleUnitTaxonomyTests(TestCase):
    def test_defaults(self) -> None:
        unit = BattleUnitFactory()
        self.assertEqual(unit.quality, UnitQuality.TRAINED)
        self.assertIsNone(unit.commander)
        self.assertIsNone(unit.summoned_by)
        self.assertEqual(unit.properties.count(), 0)
        self.assertEqual(unit.capabilities.count(), 0)
        self.assertIsNone(unit.individual_count)

    def test_commander_set_null_on_character_sheet_delete(self) -> None:
        commander = CharacterSheetFactory()
        unit = BattleUnitFactory(commander=commander)
        commander.character.delete()
        # Flush identity mapper cache so refresh_from_db picks up SET_NULL change
        BattleUnit.flush_instance_cache()
        unit.refresh_from_db()
        self.assertIsNone(unit.commander)


class BattleUnitPropertyCapabilityTests(TestCase):
    """#1794: BattleUnit holds Property/CapabilityType directly."""

    def test_has_property_true_when_attached(self) -> None:
        unit = BattleUnitFactory()
        prop = PropertyFactory()
        unit.properties.add(prop)
        self.assertTrue(unit.has_property(prop))

    def test_has_property_false_when_absent(self) -> None:
        unit = BattleUnitFactory()
        prop = PropertyFactory()
        self.assertFalse(unit.has_property(prop))

    def test_effective_capability_returns_authored_magnitude(self) -> None:
        """Two units holding the same capability at different magnitudes each
        report their own distinct value (the Garalothe-vs-Blarg case — no
        flattening to a presence bit)."""
        dragon = BattleUnitFactory(name="Garalothe the Lightning Wing")
        hedge_wizard = BattleUnitFactory(name="Blarg the Feckless")
        flight = CapabilityTypeFactory(name="flight")

        BattleUnitCapability.objects.create(unit=dragon, capability=flight, value=50)
        BattleUnitCapability.objects.create(unit=hedge_wizard, capability=flight, value=1)

        self.assertEqual(dragon.effective_capability(flight), 50)
        self.assertEqual(hedge_wizard.effective_capability(flight), 1)

    def test_effective_capability_zero_when_absent(self) -> None:
        unit = BattleUnitFactory()
        flight = CapabilityTypeFactory(name="flight")
        self.assertEqual(unit.effective_capability(flight), 0)


class BattleUnitMoraleTests(TestCase):
    def test_morale_defaults_to_default_morale_constant(self) -> None:
        from world.battles.constants import DEFAULT_MORALE

        unit = BattleUnitFactory()
        self.assertEqual(unit.morale, DEFAULT_MORALE)

    def test_morale_can_be_overridden(self) -> None:
        unit = BattleUnitFactory(morale=10)
        self.assertEqual(unit.morale, 10)


class BattlePlaceControlTests(TestCase):
    def test_controlled_by_defaults_to_none(self) -> None:
        place = BattlePlaceFactory()
        self.assertIsNone(place.controlled_by)

    def test_controlled_by_can_be_set_and_set_null_on_side_delete(self) -> None:
        from world.battles.models import BattlePlace

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        place = BattlePlaceFactory(battle=battle, controlled_by=side)
        self.assertEqual(place.controlled_by_id, side.pk)

        side.delete()
        BattlePlace.flush_instance_cache()
        place.refresh_from_db()
        self.assertIsNone(place.controlled_by)


class TechniquePropertyAffinityTests(TestCase):
    def test_unique_per_technique_property(self) -> None:
        technique = TechniqueFactory()
        prop = PropertyFactory()
        TechniquePropertyAffinity.objects.create(technique=technique, property=prop, modifier=15)
        with self.assertRaises(IntegrityError):
            TechniquePropertyAffinity.objects.create(
                technique=technique, property=prop, modifier=-5
            )


class TerrainPropertyEffectTests(TestCase):
    def test_unique_per_terrain_property(self) -> None:
        prop = PropertyFactory()
        TerrainPropertyEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, property=prop, modifier=15
        )
        with self.assertRaises(IntegrityError):
            TerrainPropertyEffect.objects.create(
                terrain_type=TerrainType.DIFFICULT, property=prop, modifier=5
            )


class FortificationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.place = BattlePlaceFactory()
        cls.side = BattleSideFactory(battle=cls.place.battle)

    def test_str_shows_integrity_when_not_breached(self):
        fort = FortificationFactory(
            place=self.place, defending_side=self.side, integrity=40, max_integrity=100
        )
        self.assertIn("40/100", str(fort))

    def test_str_shows_breached_when_breached(self):
        fort = FortificationFactory(
            place=self.place, defending_side=self.side, integrity=0, breached=True
        )
        self.assertIn("breached", str(fort))

    def test_multiple_fortifications_per_place(self):
        FortificationFactory(
            place=self.place, defending_side=self.side, kind=FortificationKind.WALL
        )
        FortificationFactory(
            place=self.place, defending_side=self.side, kind=FortificationKind.GATE
        )
        self.assertEqual(self.place.fortifications.count(), 2)


class BattleVehicleTests(TestCase):
    def test_pairs_one_unit_and_one_place(self):
        unit = BattleUnitFactory()
        place = BattlePlaceFactory(battle=unit.battle)
        vehicle = BattleVehicleFactory(unit=unit, place=place, vehicle_kind=VehicleKind.SHIP)

        self.assertEqual(vehicle.unit, unit)
        self.assertEqual(vehicle.place, place)
        self.assertTrue(vehicle.is_structural)

    def test_dragon_defaults_to_non_structural(self):
        vehicle = BattleVehicleFactory(vehicle_kind=VehicleKind.DRAGON, is_structural=False)

        self.assertFalse(vehicle.is_structural)


class BattleIsPausedFieldTests(TestCase):
    def test_defaults_to_false(self) -> None:
        battle = BattleFactory()
        assert battle.is_paused is False

    def test_can_be_set_true_and_persists(self) -> None:
        battle = BattleFactory()
        battle.is_paused = True
        battle.save(update_fields=["is_paused"])
        battle.refresh_from_db()
        assert battle.is_paused is True


class BattleMovementTransitFieldsTests(TestCase):
    def test_battle_unit_transit_fields_default_none(self) -> None:
        unit = BattleUnitFactory()
        self.assertIsNone(unit.transit_x)
        self.assertIsNone(unit.transit_y)
        self.assertIsNone(unit.transit_target_place)

    def test_battle_participant_transit_fields_default_none(self) -> None:
        participant = BattleParticipantFactory()
        self.assertIsNone(participant.transit_x)
        self.assertIsNone(participant.transit_y)
        self.assertIsNone(participant.transit_target_place)

    def test_battle_unit_transit_fields_are_settable(self) -> None:
        place = BattlePlaceFactory()
        unit = BattleUnitFactory(battle=place.battle)
        unit.transit_x = Decimal("3.50")
        unit.transit_y = Decimal("-1.25")
        unit.transit_target_place = place
        unit.save(update_fields=["transit_x", "transit_y", "transit_target_place"])
        unit.refresh_from_db()
        self.assertEqual(unit.transit_x, Decimal("3.50"))
        self.assertEqual(unit.transit_y, Decimal("-1.25"))
        self.assertEqual(unit.transit_target_place_id, place.pk)
