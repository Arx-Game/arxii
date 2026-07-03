from django.db import IntegrityError
from django.test import TestCase

from world.battles.constants import (
    BattleActionScope,
    BattleOutcome,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitComposition,
    UnitQuality,
)
from world.battles.factories import (
    BattleFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import (
    BattleUnit,
    TechniqueCompositionAffinity,
    TerrainCompositionEffect,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
from world.magic.factories import TechniqueFactory


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
        self.assertEqual(unit.composition, UnitComposition.IRREGULAR)
        self.assertEqual(unit.quality, UnitQuality.TRAINED)
        self.assertIsNone(unit.commander)
        self.assertIsNone(unit.summoned_by)

    def test_commander_set_null_on_character_sheet_delete(self) -> None:
        commander = CharacterSheetFactory()
        unit = BattleUnitFactory(commander=commander)
        commander.character.delete()
        # Flush identity mapper cache so refresh_from_db picks up SET_NULL change
        BattleUnit.flush_instance_cache()
        unit.refresh_from_db()
        self.assertIsNone(unit.commander)


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


class TechniqueCompositionAffinityTests(TestCase):
    def test_unique_per_technique_composition(self) -> None:
        technique = TechniqueFactory()
        TechniqueCompositionAffinity.objects.create(
            technique=technique, composition=UnitComposition.CAVALRY, modifier=15
        )
        with self.assertRaises(IntegrityError):
            TechniqueCompositionAffinity.objects.create(
                technique=technique, composition=UnitComposition.CAVALRY, modifier=-5
            )


class TerrainCompositionEffectTests(TestCase):
    def test_unique_per_terrain_composition(self) -> None:
        TerrainCompositionEffect.objects.create(
            terrain_type=TerrainType.DIFFICULT, composition=UnitComposition.CAVALRY, modifier=15
        )
        with self.assertRaises(IntegrityError):
            TerrainCompositionEffect.objects.create(
                terrain_type=TerrainType.DIFFICULT, composition=UnitComposition.CAVALRY, modifier=5
            )
